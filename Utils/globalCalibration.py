import asyncio
import re
import sys
import os
import csv
import statistics
from collections import deque

import numpy as np
from bleak import BleakClient
from bleak.exc import BleakError

from config import BLE_ID, UART_TX_CHAR_UUID  # <-- use your config


LINE_RE = re.compile(
    r"Time:(-?\d+),V1:(-?\d+(?:\.\d+)?),V2:(-?\d+(?:\.\d+)?),V3:(-?\d+(?:\.\d+)?),V4:(-?\d+(?:\.\d+)?)"
)
def calculate_v3_median(samples):
    if not samples:
        return float("nan")
    return statistics.median([row[1] for row in samples])

async def record_v3_until_enter(prompt_msg, client: BleakClient, tx_uuid: str):
    samples = []
    v3_hist = deque(maxlen=3)

    def notification_handler(sender: int, data: bytearray):
        line = data.decode("utf-8", errors="ignore").strip()
        m = LINE_RE.match(line)
        if not m:
            return
        try:
            t_ms = int(m.group(1))
            v3_raw = float(m.group(4))
        except Exception:
            return

        v3_hist.append(v3_raw)
        v3_smooth = float(np.median(v3_hist)) if len(v3_hist) == v3_hist.maxlen else v3_raw
        samples.append([t_ms, v3_smooth])

    await client.start_notify(tx_uuid, notification_handler)

    print(prompt_msg, end="", flush=True)
    await asyncio.to_thread(sys.stdin.readline)

    try:
        await client.stop_notify(tx_uuid)
    except Exception:
        pass

    await asyncio.sleep(0.1)
    return samples

async def main():
    print(f"Connecting directly to: {BLE_ID}")

    try:
        async with BleakClient(BLE_ID, timeout=20.0) as client:
            print(BLE_ID)
            if not client.is_connected:
                print("Failed to connect.")
                sys.exit(1)

            print("✅ Connected.")

            session_label = input("Enter a 2-character label for this sensor calibration: ").strip().upper()
            if len(session_label) != 2:
                print("Label must be exactly 2 characters.")
                return

            os.makedirs("calibrationWeight", exist_ok=True)

            print("\nStart with NO weight on the force Sensor (nothing touching).")
            baseline_samples = await record_v3_until_enter(
                "Recording baseline... Press Enter when stable.\n",
                client,
                UART_TX_CHAR_UUID,
            )
            baseline_v3_mean = calculate_v3_median(baseline_samples)
            print(f"Baseline V3 mean: {baseline_v3_mean:.2f}\n")

            weight_kg = float(input("Place the FIRST known weight (kg) attached to the force Sensor: "))
            weight_N = weight_kg * 9.81

            first_samples = await record_v3_until_enter(
                f"Recording for {weight_kg:.2f} kg... Press Enter when stable.\n",
                client,
                UART_TX_CHAR_UUID,
            )
            first_v3_mean = calculate_v3_median(first_samples)
            print(f"V3 mean: {first_v3_mean:.2f}\n")

            forces = [0.0, weight_N]
            v3_means = [baseline_v3_mean, first_v3_mean]

            while True:
                entry = input("Enter another weight in kg (centered) — or press Enter to finish: ").strip()
                if not entry:
                    break
                try:
                    w_kg = float(entry)
                    w_N = w_kg * 9.81

                    samples = await record_v3_until_enter(
                        f"Recording for {w_kg:.2f} kg... Press Enter when stable.\n",
                        client,
                        UART_TX_CHAR_UUID,
                    )
                    v3_mean = calculate_v3_median(samples)

                    forces.append(w_N)
                    v3_means.append(v3_mean)
                    print(f"V3 mean: {v3_mean:.2f}\n")
                except Exception:
                    print("Invalid input. Try again.")

            filename = f"calibrationWeight/{session_label}_calibration.csv"
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Force_N", "V3_mean"])
                for f_n, v in zip(forces, v3_means):
                    writer.writerow([round(f_n, 3), round(v, 2)])

            print(f"\nCalibration data saved to {filename}")

    except (BleakError, Exception) as e:
        print(f"BLE error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())