# controllers/sensor_controller.py

import asyncio
import time
import os
import csv
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError, BleakDBusError
import sys 
import numpy as np
from datetime import date

# NOTE: The UART_TX_CHAR_UUID should ideally be imported from utils/config.py
# Assuming it's passed via the tx_uuid parameter for flexibility.
# UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E" 

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
    Manages the asynchronous BLE connection (View/Connect) and concurrent 
    data acquisition (Model/Read) for the Force Sensor.
    """
    
    def __init__(self, ble_address, tx_uuid):
        self.ble_address = ble_address
        self.tx_uuid = tx_uuid
        self.client = None
        self.is_connected = False 
        self.is_reading = False       # Flag to control data logging
        self.collected_data = []      # Container for data
        self.start_time_host_s = 0.0  # Host time when recording officially starts

    # --- Data Acquisition Handler ---
    def notification_handler(self, sender: int, data: bytearray):
        """
        Called every time the BLE device sends data.
        Logs data only if the self.is_reading flag is True.
        """
        host_time = time.time()
        
        if self.is_reading:
            try:
                decoded_data = data.decode('utf-8', errors='ignore').strip()
                # Log Host Timestamp and Raw Data Line
                self.collected_data.append((host_time, decoded_data))
            except Exception:
                # Log raw bytes if decoding fails
                self.collected_data.append((host_time, str(data)))

    # --- 1. Connection/Disconnection Methods ---
    
    async def connect_device(self):
        """
        Establishes the BLE connection and enables notifications. 
        Returns immediately (True/False) without looping.
        """
        if self.client:
            # Should not happen if disconnect_device was called, but a safety
            await self.client.disconnect()
            self.client = None
            print("emptied client")
            
        print(f"\n[SENSOR] Attempting connection to BLE address: {self.ble_address}...")
        try:
            device = await BleakScanner.find_device_by_address(self.ble_address, timeout=10.0)
            if not device:
                raise BleakError(f"A device with address {self.ble_address} could not be found.")
            
            # Use force_disconnect=True for robustness
            self.client = BleakClient(device, timeout=22.0, force_disconnect=True)
            await self.client.connect()

            if not self.client.is_connected:
                 print("[SENSOR] ❌ Failed to connect.")
                 self.is_connected = False
                 return False
            
            # CRITICAL: Start notify immediately upon successful connection.
            # This enables the flow to the notification_handler.
            await self.client.start_notify(self.tx_uuid, self.notification_handler)
            print("[SENSOR] ✅ Connection established. Notifications activated.")
            self.is_connected = True
            
            return True

        except (BleakError, BleakDBusError) as e:
            print(f"[SENSOR] ❌ Connection/Discovery Error: {e}")
            self.is_connected = False
            return False
        except Exception as e:
            print(f"[SENSOR] ❌ An unexpected error occurred: {e}")
            self.is_connected = False
            return False

    async def disconnect_device(self):
        """Stops notifications and physically disconnects the client."""
        if self.is_connected:
            if self.client and self.client.is_connected:
                try:
                    await self.client.stop_notify(self.tx_uuid)
                except Exception:
                    pass
                await self.client.disconnect()
            
            self.is_connected = False
            print("[SENSOR] Explicitly disconnected.")
            return True
        return False
    
    # Alias 'close' to 'disconnect_device' for compatibility with the orchestrator
    close = disconnect_device

    # --- 2. Data Acquisition Methods (Reading/Logging) ---
    
    async def start_reading(self):
        """Starts the process of logging sensor data by flipping the internal flag."""
        if self.client and self.client.is_connected:
            self.collected_data.clear()
            self.start_time_host_s = time.time() # Record the precise host time of start
            self.is_reading = True
            print(f"[SENSOR] Data logging started. Timestamp: {self.start_time_host_s:.6f} s.")
            return True
        return False
    
    async def stop_reading(self, distance_cm: float, speed_mps: float, weight_kg: int, turf_id: str) -> bool:
        """Stops the data logging process and triggers the synchronous save function."""
        self.is_reading = False
        print("[SENSOR] Data logging stopped. Saving data...")

        # Offload the saving work to a thread. Note: pass the function *without* calling it.
        await asyncio.to_thread(
            self._save_data,
            self.collected_data,
            self.start_time_host_s,
            distance_cm,
            speed_mps,
            weight_kg,
            turf_id
        )

        return True
    
    
    def _save_data(self, log_data, start_time, speed_mps, distance_cm, weight_kg, turf_id):
        os.makedirs("readings", exist_ok=True)

        today_str = date.today().isoformat()  # "YYYY-MM-DD"
        turf_id = (turf_id or "").strip()

        # Find an existing folder in readings that contains both today and turf_id
        save_dir = None
        for name in os.listdir("readings"):
            path = os.path.join("readings", name)
            if os.path.isdir(path) and (today_str in name) and (turf_id in name):
                save_dir = path
                break

        # If none found, create a new one named "<today>_<turf_id>"
        if save_dir is None:
            folder_name = f"{today_str}_{turf_id}" if turf_id else today_str
            save_dir = os.path.join("readings", folder_name)
            os.makedirs(save_dir, exist_ok=True)

        timestamp_s = int(time.time())
        speed_str = f"{speed_mps:.4f}".replace(".", "p")

        filename = os.path.join(
            save_dir,
            f"{timestamp_s}_{int(distance_cm)}cm_{speed_str}mps_{weight_kg}kg_grip_data.csv"
        )

        after_start = [(host_time, line) for host_time, line in log_data if host_time >= start_time]
        if not after_start:
            print(f"[SAVE] Data log found ({len(log_data)} entries), but none were recorded after start time ({start_time:.6f} s).")
            return

        raw_values = np.array([line for _, line in after_start], dtype=float)
        filtered_values = hampel_filter(raw_values, window_size=11, n_sigmas=5.0)

        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Host_Time_s", "Raw_Data_Line", "Filtered_Line"])
            for (host_time, raw_line), filt_line in zip(after_start, filtered_values):
                writer.writerow([f"{host_time:.6f}", raw_line, int(filt_line)])

        print(f"\n[SAVE] Saved {len(after_start)} data points to {filename}")
        