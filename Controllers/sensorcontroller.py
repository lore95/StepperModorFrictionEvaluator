# Controllers/sensorcontroller.py

import asyncio
import time
import os
import csv
import numpy as np
from datetime import date
import re
from typing import Callable, Optional, Awaitable, Any, Dict

from bleak import BleakClient
from bleak.exc import BleakError, BleakDBusError

from Utils.sensorForceConverter import V3ForceCalibrator


LINE_RE = re.compile(
    r"Time:(-?\d+),V1:(-?\d+(?:\.\d+)?),V2:(-?\d+(?:\.\d+)?),V3:(-?\d+(?:\.\d+)?),V4:(-?\d+(?:\.\d+)?)"
)


def hampel_filter(vals, window_size=11, n_sigmas=5.0):
    """Simple Hampel filter to remove spikes."""
    n = len(vals)
    half_w = window_size // 2
    k = 1.4826
    filtered = vals.copy()
    for i in range(n):
        start = max(0, i - half_w)
        end = min(n, i + half_w + 1)
        window = vals[start:end]
        med = np.median(window)
        mad = np.median(np.abs(window - med))
        if mad == 0:
            continue
        threshold = n_sigmas * k * mad
        if abs(vals[i] - med) > threshold:
            filtered[i] = med
    return filtered


class AsyncSensorReader:
    """
    BLE sensor reader with:
      - start_notify handler to collect raw + force
      - unexpected disconnect handling via Bleak disconnected_callback
      - optional async prompt_save_cb (must be thread-safe)
    """

    def __init__(
        self,
        ble_address: str,
        tx_uuid: str,
        ble_loop: asyncio.AbstractEventLoop,
        *,
        prompt_save_cb: Optional[Callable[[], Awaitable[bool]]] = None,
        calibration_csv: str = "Utils/calibrationWeight/V3_calibration.csv",
    ):
        self.ble_address = ble_address
        self.tx_uuid = tx_uuid
        self.ble_loop = ble_loop

        self.client: Optional[BleakClient] = None
        self.is_connected = False
        self.is_reading = False
        self.offSetValue = 0.0

        self.collected_raw_data = []    # list[(host_time_s, raw_v3)]
        self.collected_force_data = []  # list[(host_time_s, force_n)]
        self.start_time_host_s = 0.0

        self.calibrator = V3ForceCalibrator(
            calibration_csv,
            method="piecewise",
            allow_extrapolation=True,
        )

        self.prompt_save_cb = prompt_save_cb
        self._disconnect_lock = asyncio.Lock()
        # Used when disconnect happens mid-run and you want to save partial
        self._pending_meta: Dict[str, Any] = {
            "distance_cm": 0.0,
            "speed_mps": 0.0,
            "weight_kg": 0,
            "turf_id": "ERROR",
        }

    # -------------------- Notifications --------------------
    def notification_handler(self, sender: int, data: bytearray):
        host_time = time.time()
        if not self.is_reading:
            return

        try:
            line = data.decode("utf-8", errors="ignore").strip()
            m = LINE_RE.match(line)
            if not m:
                return

            t_ms = int(m.group(1))
            v3_raw = float(m.group(4))

            self.collected_raw_data.append((host_time, v3_raw))

            v3_force = self.calibrator.raw_to_force(v3_raw,self.offSetValue)

            self.collected_force_data.append((host_time, v3_force))

        except Exception as e:
            print(f"[SENSOR] notification_handler error: {e}")

    # -------------------- Disconnect handling --------------------
    def _on_disconnect(self, _client: BleakClient):
        print("[SENSOR] ⚠️ Device disconnected unexpectedly.")

        try:
            asyncio.run_coroutine_threadsafe(
                self._handle_disconnect(),
                self.ble_loop,   # ✅ USE THE STORED LOOP
            )
        except Exception as e:
            print(f"[SENSOR] Failed to schedule disconnect handler: {e}")
            self.is_connected = False
            self.is_reading = False

    async def _handle_disconnect(self):
        try:
            async with self._disconnect_lock:
                was_reading = self.is_reading

                self.is_connected = False
                self.is_reading = False
                print("[SENSOR] Handling disconnect...")
                
                # Ask UI whether to save (defaults to True if no callback)
                save = True
                if self.prompt_save_cb is not None:
                    try:
                        save = await self.prompt_save_cb()
                    except Exception as e:
                        print(f"[SENSOR] prompt_save_cb failed: {e}")
                        save = True

                # Clear client reference (it may already be dead)
                if self.client:
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                    self.client = None

                if not was_reading:
                    self._clear_buffers()
                    print("[SENSOR] buffers cleared")
                    return

                if save:
                    print("[SENSOR] User chose to save partial data.")
                    meta = dict(self._pending_meta)
                    await asyncio.to_thread(
                        self._save_data,
                        self.collected_raw_data,
                        self.collected_force_data,
                        self.start_time_host_s,
                        self.
                        meta.get("speed_mps", 0.0),
                        meta.get("distance_cm", 0.0),
                        meta.get("weight_kg", 0),
                        meta.get("turf_id", "DISCONNECT"),
                    )
                    self._clear_buffers()
                else:
                    print("[SENSOR] User chose NOT to save. Clearing buffers.")
                    self._clear_buffers()

        except Exception as e:
            print(f"[SENSOR] _handle_disconnect crashed: {e}")

    def _clear_buffers(self):
        self.collected_raw_data.clear()
        self.collected_force_data.clear()
        self._pending_meta = {
            "distance_cm": 0.0,
            "speed_mps": 0.0,
            "weight_kg": 0,
            "turf_id": "UNKNOWN",
        }

    # -------------------- Connect / Disconnect --------------------
    async def connect_device(self) -> bool:
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None

        print(f"\n[SENSOR] Attempting connection to BLE address: {self.ble_address}...")
        try:
            self.client = BleakClient(
                self.ble_address,
                timeout=20.0,
                disconnected_callback=self._on_disconnect,  # ✅ critical
            )
            await self.client.connect()

            if not self.client.is_connected:
                print("[SENSOR] Failed to connect.")
                self.is_connected = False
                return False
            baseline_samples = []
            print("[SENSOR] Calibrating base line for force convertion ")

            def _baseline_handler(sender: int, data: bytearray):
                try:
                    line = data.decode("utf-8", errors="ignore").strip()
                    m = LINE_RE.match(line)
                    if not m:
                        return
                    v3_raw = float(m.group(4))
                    baseline_samples.append(v3_raw)
                except Exception:
                    return
            await self.client.start_notify(self.tx_uuid, _baseline_handler)
            print("[SENSOR] Collecting baseline for 5 seconds...")
            await asyncio.sleep(5.0)

            # Stop temporary notify
            try:
                await self.client.stop_notify(self.tx_uuid)
            except Exception:
                pass

            if baseline_samples:
                self.offSetValue = float(np.median(np.array(baseline_samples, dtype=float)))
                print(f"[SENSOR] Baseline median set: offSetValue={self.offSetValue:.3f} (n={len(baseline_samples)})")
            else:
                self.offSetValue = 0.0
                print("[SENSOR] No baseline samples received. offSetValue set to 0.0")

            
            await self.client.start_notify(self.tx_uuid, self.notification_handler)
            print("[SENSOR] ✅ Connected. Notifications activated.")
            self.is_connected = True

            return True

        except (BleakError, BleakDBusError) as e:
            print(f"[SENSOR] ❌ Connection/Discovery Error: {e}")
            self.is_connected = False
            self.client = None
            return False
        except Exception as e:
            print(f"[SENSOR] ❌ Unexpected error: {e}")
            self.is_connected = False
            self.client = None
            return False

    async def disconnect_device(self) -> bool:
        # Intentional disconnect: no popup
        self.is_reading = False

        if self.client:
            try:
                await self.client.stop_notify(self.tx_uuid)
            except Exception:
                pass
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None

        self.is_connected = False
        print("[SENSOR] Explicitly disconnected.")
        return True

    close = disconnect_device

    # -------------------- Reading control --------------------
    async def start_reading(
        self,
        *,
        distance_cm: float = 0.0,
        speed_mps: float = 0.0,
        weight_kg: int = 0,
        turf_id: str = "UNKNOWN",
        direction: int = 0
    ) -> bool:
        if self.client and self.client.is_connected:
            self.collected_raw_data.clear()
            self.collected_force_data.clear()
            self.start_time_host_s = time.time()
            if(direction == 0):
                self.is_reading = True
            self._pending_meta = {
                "distance_cm": float(distance_cm),
                "speed_mps": float(speed_mps),
                "weight_kg": int(weight_kg),
                "turf_id": str(turf_id or "UNKNOWN"),
            }
            if(direction == 0):
                print(f"[SENSOR] Data logging started. Timestamp: {self.start_time_host_s:.6f} s.")
            return True
        return False

    async def stop_reading(self, distance_cm: float, speed_mps: float, weight_kg: int, turf_id: str) -> bool:
        self.is_reading = False
        print("[SENSOR] Data logging stopped. Saving data...")

        await asyncio.to_thread(
            self._save_data,
            self.collected_raw_data,
            self.collected_force_data,
            self.start_time_host_s,
            speed_mps,
            distance_cm,
            weight_kg,
            turf_id,
        )
        self._clear_buffers()
        return True

    # -------------------- Save --------------------
    def _save_data(
        self,
        log_raw_data,
        log_force_data,
        start_time,
        distance_cm,
        speed_mps,
        weight_kg,
        turf_id,
    ):
        os.makedirs("readings", exist_ok=True)
        print("Speed: " + str(speed_mps))
        print("distnace: " + str(distance_cm))
        print("weight: " + str(weight_kg))
        today_str = date.today().isoformat()
        turf_id = (turf_id or "").strip()

        save_dir = None
        for name in os.listdir("readings"):
            path = os.path.join("readings", name)
            if os.path.isdir(path) and (today_str in name) and (turf_id in name):
                save_dir = path
                break

        if save_dir is None:
            folder_name = f"{today_str}_{turf_id}" if turf_id else today_str
            save_dir = os.path.join("readings", folder_name)
            os.makedirs(save_dir, exist_ok=True)

        timestamp_s = int(time.time())
        speed_str = f"{float(speed_mps):.4f}".replace(".", "p")

        filename = os.path.join(
            save_dir,
            f"{timestamp_s}_{int(distance_cm)}cm_{speed_str}mps_{int(weight_kg)}kg_grip_data.csv"
        )

        combined = [
            (t_raw, raw, force)
            for (t_raw, raw), (t_force, force) in zip(log_raw_data, log_force_data)
            if t_raw >= start_time
        ]

        if not combined:
            print(
                f"[SAVE] Data log found ({len(log_raw_data)} entries), "
                f"but none were recorded after start time ({start_time:.6f} s)."
            )
            return

        raw_values = np.array([raw for _, raw, _ in combined], dtype=float)
        filtered_raw = hampel_filter(raw_values, window_size=11, n_sigmas=5.0)

        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Host_Time_s", "Raw_V3", "Force_N", "Raw_V3_Filtered"])
            for (host_time, raw, force), raw_filt in zip(combined, filtered_raw):
                writer.writerow([f"{host_time:.6f}", float(raw), float(force), float(raw_filt)])

        print(f"\n[SAVE] Saved {len(combined)} data points to {filename}")