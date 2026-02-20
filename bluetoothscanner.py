import asyncio
from bleak import BleakClient

BLE_ID = "09916A0D-1C88-FFB7-9BCC-005191B357F9"

TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # notify (device -> PC)
RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # write  (PC -> device)

def on_notify(sender, data: bytearray):
    print("NOTIFY:", data.decode("utf-8", errors="ignore").rstrip())

async def main():
    async with BleakClient(BLE_ID, timeout=20.0) as client:
        print("Connected:", client.is_connected)

        # Optional: print what services/characteristics were discovered
        services = client.services
        for service in services:
            print(f"SERVICE {service.uuid}")
            for char in service.characteristics:
                print(f"  CHAR {char.uuid}  props={char.properties}")

        # Subscribe to the notify characteristic (TX)
        await client.start_notify(TX_UUID, on_notify)
        print("Subscribed to TX notifications")

        # Optional: send something to RX (your firmware prints it)
        await client.write_gatt_char(RX_UUID, b"123")
        print("Wrote '123' to RX")

        # Keep alive to receive notifications
        await asyncio.sleep(10)

asyncio.run(main())