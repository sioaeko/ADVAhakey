"""Connect a known paired address without scanning an already-connected HID.

Bleak 2.1.1's Windows backend otherwise scans before opening a string address.
The adapter uses that version's numeric-address field; keep the dependency pinned.
All pairing, GATT and lifetime handling remains in Bleak/Windows.
"""
from bleak.backends.winrt.client import BleakClientWinRT


class AddressWinRTClient(BleakClientWinRT):
    def __init__(self, device, **kwargs):
        super().__init__(device, **kwargs)
        if isinstance(device, str):
            parts = device.split(':')
            if len(parts) != 6 or any(len(p) != 2 for p in parts):
                raise ValueError('Bluetooth address must use AA:BB:CC:DD:EE:FF format')
            self._device_info = int(''.join(parts), 16)
