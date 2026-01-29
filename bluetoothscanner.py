import asyncio
from bleak import BleakScanner

async def main():
    devices = await BleakScanner.discover()
    for d in devices:
        if(d.address == "6375EA4B-23F2-5C9E-249F-5EC7660C1DA1"):
            print(d.name)

asyncio.run(main())