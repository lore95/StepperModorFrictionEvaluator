# controllers/sensor_controller.py

import asyncio
import time
import os
import csv
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError, BleakDBusError
import sys 

# NOTE: The UART_TX_CHAR_UUID should ideally be imported from utils/config.py
# Assuming it's passed via the tx_uuid parameter for flexibility.
# UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E" 

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
        
    async def stop_reading(self):
        """Stops the data logging process and triggers the synchronous save function."""
        self.is_reading = False
        print("[SENSOR] Data logging stopped. Saving data...")
        
        # Run the saving function synchronously in a separate thread
        await asyncio.to_thread(self._save_data, self.collected_data, self.start_time_host_s)
        
        return True

    def _save_data(self, log_data, start_time):
        """Filters data logged after the motor started and saves to a CSV file (Synchronous)."""
        if not log_data:
            print("[SAVE] No data recorded to save.")
            return

        # 1. Create directory and filename
        os.makedirs('readings', exist_ok=True)
        timestamp_s = int(time.time())
        filename = os.path.join('readings', f'{timestamp_s}_grip_data.csv')
        
        # 2. Filter data logged after the recording started
        filtered_data = [
            (host_time, line) for host_time, line in log_data 
            if host_time >= start_time
        ]
        
        if not filtered_data:
            print(f"[SAVE] Data log found ({len(log_data)} entries), but none were recorded after start time ({start_time:.6f} s).")
            return

        # 3. Save to CSV
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Host_Time_s', 'Raw_Data_Line']) # Header
            
            for host_time, line in filtered_data:
                writer.writerow([f"{host_time:.6f}", line])
                
        print(f"\n[SAVE] Successfully saved {len(filtered_data)} data points to {filename}")