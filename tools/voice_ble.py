"""Paired BLE GATT transport for ADV audio; no Wi-Fi, sockets or cloud service."""
import asyncio
import logging
import secrets
import struct
import sys
import threading
import time

SERVICE = 'c0a17340-7d8e-4a15-9f4a-2b0c73a10000'
AUDIO = 'c0a17341-7d8e-4a15-9f4a-2b0c73a10000'
CONTROL = 'c0a17342-7d8e-4a15-9f4a-2b0c73a10000'
STATUS = struct.Struct('<4sIHH')
MAX_PENDING = 182 * 100  # Two seconds of ADPCM; bound stale audio.


class ReceiveBuffer:
    """Publish generation together with bytes, avoiding disconnect/read races."""
    def __init__(self, limit=MAX_PENDING):
        self.limit = limit
        self.condition = threading.Condition()
        self.data = bytearray()
        self.epoch = 0
        self.accepting = False

    def reset(self, accepting=False):
        with self.condition:
            self.data.clear()
            self.epoch += 1
            self.accepting = accepting
            self.condition.notify_all()

    def push(self, data):
        with self.condition:
            if not self.accepting:
                return False
            if len(self.data) + len(data) > self.limit:
                self.data.clear()
                self.epoch += 1
                self.accepting = False
                self.condition.notify_all()
                return False
            self.data.extend(data)
            self.condition.notify_all()
            return True

    def read(self, count, previous, timeout=.05):
        with self.condition:
            if not self.data and self.epoch == previous:
                self.condition.wait(timeout)
            result = bytes(self.data[:count])
            del self.data[:count]
            return self.epoch, result


def validate_status(data, token):
    if len(data) != STATUS.size:
        raise ConnectionError('Unsupported BLE audio status; install the Bluetooth firmware')
    magic, owner, mtu, flags = STATUS.unpack(data)
    if magic != b'AVS1':
        raise ConnectionError('Unsupported BLE audio protocol')
    if owner != token:
        raise ConnectionError('Another voice companion owns the microphone; close it first')
    if mtu < 185:
        raise ConnectionError(f'Bluetooth MTU {mtu} is too small for PCM audio (need 185)')
    if not flags & 1:
        raise ConnectionError('BLE audio subscription is not ready')
    return mtu


async def paired_windows_devices():
    """HID can already be connected, so a paired ADV may not be advertising."""
    if sys.platform != 'win32':
        return []
    from winrt.windows.devices.bluetooth import BluetoothLEDevice
    from winrt.windows.devices.enumeration import DeviceInformation
    selector = BluetoothLEDevice.get_device_selector_from_pairing_state(True)
    devices = await DeviceInformation.find_all_async_aqs_filter(selector)
    result = []
    for info in devices:
        if not info.name.startswith('AhaKey ADV'):
            continue
        device = await BluetoothLEDevice.from_id_async(info.id)
        if device is not None:
            try:
                address = f'{device.bluetooth_address:012X}'
                result.append(':'.join(address[i:i+2] for i in range(0, 12, 2)))
            finally:
                device.close()
    return list(dict.fromkeys(result))


async def find_device(scanner):
    paired = await paired_windows_devices()
    if len(paired) == 1:
        return paired[0]
    if len(paired) > 1:
        raise ConnectionError('Multiple paired ADVs; select one with --ble-address')
    found = await scanner.discover(timeout=8, return_adv=True)
    candidates = [d for d, a in found.values()
                  if (a.local_name or d.name or '').startswith('AhaKey ADV')
                  or SERVICE in a.service_uuids]
    if len(candidates) != 1:
        raise ConnectionError(f'Found {len(candidates)} ADVs; pair the keyboard in Windows or use --ble-address')
    return candidates[0]


class BleTransport:
    def __init__(self, address=None, *, client_factory=None, scanner=None, retry_delay=3,
                 log=None, buffer_limit=MAX_PENDING):
        self.address = address
        self._factory, self._scanner = client_factory, scanner
        self._retry_delay = retry_delay
        self._log = log or (lambda message: print(message, flush=True))
        self._buffer = ReceiveBuffer(buffer_limit)
        self.generation = 0  # Only read() publishes this, paired with its returned bytes.
        self._thread = self._loop = self._task = None
        self._started = threading.Event()
        self._closing = threading.Event()
        self._error = None
        self._last_poll = time.monotonic()
        self._token = secrets.randbits(32) or 1

    def __enter__(self):
        if self._factory is None:
            from bleak import BleakClient, BleakScanner
            if sys.platform == 'win32':
                from ble_windows import AddressWinRTClient
                self._factory = lambda target, **kwargs: BleakClient(target, backend=AddressWinRTClient, **kwargs)
            else:
                self._factory = BleakClient
            self._scanner = BleakScanner
        if self._thread is not None:
            raise RuntimeError('BLE transport is already open')
        self._thread = threading.Thread(target=self._thread_main, name='adv-ble', daemon=True)
        self._thread.start()
        if not self._started.wait(5):
            self.close()
            raise RuntimeError('Bluetooth worker did not start')
        return self

    def _thread_main(self):
        try:
            asyncio.run(self._run())
        except BaseException as exc:
            self._error = exc
        finally:
            self._started.set()
            self._buffer.reset()

    async def _run(self):
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.current_task()
        self._started.set()
        last_error = None
        try:
            while not self._closing.is_set():
                try:
                    target = self.address or await asyncio.wait_for(find_device(self._scanner), 20)
                    await self._connection(target)
                    last_error = None
                except Exception as exc:
                    message = f'Bluetooth: {exc}'
                    if message != last_error:
                        logging.getLogger(__name__).debug('BLE connection attempt failed', exc_info=True)
                        self._log(message)
                        last_error = message
                if not self._closing.is_set():
                    await asyncio.sleep(self._retry_delay)
        except asyncio.CancelledError:
            pass

    async def _connection(self, target):
        lost = asyncio.Event()
        subscribed = False
        owns_lease = False
        overflow = False
        active = False
        # Query only our service: enumerating all cached HID services after a
        # firmware upgrade can fail in Windows with E_UNEXPECTED.
        client = self._factory(target, pair=True, timeout=30, services=[SERVICE],
                               disconnected_callback=lambda _: lost.set(),
                               winrt={'use_cached_services': False})

        def receive(_, data):
            nonlocal overflow
            if not active:
                return  # Late callback from a closed link must not enter a new take.
            if not self._buffer.push(data):
                overflow = True
                lost.set()

        async def heartbeat():
            await client.write_gatt_char(CONTROL, struct.pack('<4sI', b'AVH1', self._token), response=True)
            status = await client.read_gatt_char(CONTROL)
            return validate_status(status, self._token)

        try:
            await asyncio.wait_for(client.connect(), 45)
            if not client.services.get_characteristic(CONTROL) or not client.services.get_characteristic(AUDIO):
                raise ConnectionError('ADV has no BLE microphone service; install the 1.4.0-ble firmware')
            # Claim first, then subscribe. A second process must not toggle the first
            # process's CCCD subscription during cleanup.
            await asyncio.wait_for(client.write_gatt_char(
                CONTROL, struct.pack('<4sI', b'AVH1', self._token), response=True), 2)
            raw = await asyncio.wait_for(client.read_gatt_char(CONTROL), 2)
            if len(raw) != STATUS.size or STATUS.unpack(raw)[0:2] != (b'AVS1', self._token):
                raise ConnectionError('Another companion owns BLE audio, or the firmware is incompatible')
            owns_lease = True
            self._buffer.reset(accepting=True)
            active = True
            await asyncio.wait_for(client.start_notify(AUDIO, receive), 3)
            subscribed = True
            mtu = await asyncio.wait_for(heartbeat(), 2)
            self._log(f'Bluetooth audio ready: {getattr(target, "address", target)}; MTU {mtu}; Wi-Fi unused')
            while client.is_connected and not lost.is_set():
                try:
                    await asyncio.wait_for(lost.wait(), .75)
                except asyncio.TimeoutError:
                    # Do not keep a microphone lease alive if the consumer has stalled.
                    if time.monotonic() - self._last_poll > 2.5:
                        raise ConnectionError('Audio consumer stopped polling')
                    await asyncio.wait_for(heartbeat(), 2)
            if overflow:
                raise ConnectionError('Audio receive buffer overflow; incomplete recording discarded')
            raise ConnectionError('ADV disconnected; waiting to reconnect')
        finally:
            active = False
            self._buffer.reset()
            if client.is_connected:
                if owns_lease:
                    try:
                        await asyncio.wait_for(client.write_gatt_char(
                            CONTROL, struct.pack('<4sI', b'AVH0', self._token), response=True), 1)
                    except Exception:
                        pass
                if subscribed:
                    try:
                        await asyncio.wait_for(client.stop_notify(AUDIO), 1)
                    except Exception:
                        pass
            try:
                await asyncio.wait_for(client.disconnect(), 3)
            except Exception:
                pass

    def write(self, data):
        if data != b'AHA-MIC\n':
            raise ValueError('BLE transport only accepts microphone heartbeats')
        self._last_poll = time.monotonic()
        return len(data)

    def read(self, count):
        if count <= 0:
            return b''
        if self._error is not None:
            raise RuntimeError('Bluetooth worker stopped') from self._error
        self._last_poll = time.monotonic()
        self.generation, result = self._buffer.read(count, self.generation)
        return result

    def close(self):
        self._closing.set()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._task.cancel)
        if self._thread is not None:
            self._thread.join(8)
            if self._thread.is_alive():
                raise RuntimeError('Bluetooth worker did not stop within 8 seconds')
        self._buffer.reset()

    def __exit__(self, *_):
        self.close()
