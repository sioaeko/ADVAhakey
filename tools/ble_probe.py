"""Read-only live AhaKey BLE diagnostic; install bleak first."""
import asyncio
from bleak import BleakClient, BleakScanner

UUID = lambda short: f'0000{short}-0000-1000-8000-00805f9b34fb'
async def main():
    found = await BleakScanner.discover(timeout=8, return_adv=True)
    candidates = [d for d, a in found.values() if (a.local_name or d.name or '').startswith('AhaKey ADV')]
    if len(candidates) != 1:
        raise SystemExit(f'Expected exactly one AhaKey ADV, found {len(candidates)}. Close other BLE clients if necessary.')
    event = asyncio.Event()
    def notify(_, data):
        if len(data) == 13 and data[:3] == bytes.fromhex('aabb00') and data[-2:] == bytes.fromhex('ccdd'):
            print(dict(battery=data[3], firmware=f'{data[5]}.{data[6]}', mode=data[7], effect=data[8], switch=data[9], brightness=data[10]))
            event.set()
    async with BleakClient(candidates[0]) as client:
        await client.start_notify(UUID('7344'), notify)
        await client.write_gatt_char(UUID('7343'), bytes.fromhex('aabb00ccdd'), response=True)
        await asyncio.wait_for(event.wait(), 5)
        await client.stop_notify(UUID('7344'))
if __name__ == '__main__':
    asyncio.run(main())
