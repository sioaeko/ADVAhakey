import asyncio
from pathlib import Path
import struct
import sys
import threading
import time
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
from voice_ble import AUDIO, CONTROL, SERVICE, STATUS, BleTransport, ReceiveBuffer, find_device, validate_status
from voice_protocol import Decoder
from test_voice import frame


class BufferTests(unittest.TestCase):
    def test_disconnect_cannot_attach_old_bytes_to_new_generation(self):
        b = ReceiveBuffer()
        b.reset(True)
        b.push(b'old')
        generation, data = b.read(9, 0)
        b.reset(True)
        b.push(b'new')
        self.assertEqual(data, b'old')
        new_generation, new_data = b.read(9, generation)
        self.assertGreater(new_generation, generation)
        self.assertEqual(new_data, b'new')

    def test_overflow_discards_entire_session_until_reset(self):
        b = ReceiveBuffer(5)
        b.reset(True)
        self.assertTrue(b.push(b'1234'))
        generation = b.epoch
        self.assertFalse(b.push(b'56'))
        self.assertFalse(b.push(b'7'))
        self.assertEqual(b.read(9, generation)[1], b'')
        self.assertGreater(b.epoch, generation)
        b.reset(True)
        self.assertTrue(b.push(b'new'))

    def test_all_ble_fragment_sizes_preserve_full_minute_pcm(self):
        pcm = bytes(range(160)) * 2
        stream = frame(1, 0) + b''.join(frame(2, n, pcm) for n in range(1, 6001)) + frame(3, 6001)
        for size in (20, 182, 244, 339):
            with self.subTest(size=size):
                d = Decoder()
                completed = []
                for offset in range(0, len(stream), size):
                    completed += d.feed(stream[offset:offset+size])
                self.assertEqual(completed, [pcm * 6000])
                self.assertEqual(d.errors, 0)

    def test_lost_fragment_never_completes_take(self):
        packet = frame(2, 1, b'a' * 320)
        d = Decoder()
        self.assertEqual(d.feed(frame(1, 0) + packet[:182] + frame(3, 2)), [])
        self.assertIsNotNone(d.session)  # Truncated frame waits; consumer timeout discards it.
        self.assertEqual(d.feed(frame(1, 0, session=4) + frame(2, 1, b'b'*320, session=4) + frame(3, 2, session=4)), [b'b'*320])

    def test_status_rejects_wrong_owner_mtu_and_subscription(self):
        self.assertEqual(validate_status(STATUS.pack(b'AVS1', 9, 185, 1), 9), 185)
        for status in (b'', STATUS.pack(b'xxxx', 9, 185, 1),
                       STATUS.pack(b'AVS1', 8, 185, 1), STATUS.pack(b'AVS1', 9, 23, 1),
                       STATUS.pack(b'AVS1', 9, 185, 0)):
            with self.subTest(status=status), self.assertRaises(ConnectionError):
                validate_status(status, 9)


class FakeClient:
    def __init__(self, factory, target, **kwargs):
        self.factory = factory
        self.kwargs = kwargs
        self.is_connected = False
        self.callback = None
        self.token = 0
        self.writes = []
        self.services = self
        self.stopped_notify = False
        self.disconnected = False
        factory.clients.append(self)

    def get_characteristic(self, uuid):
        return uuid if self.factory.has_service else None

    async def connect(self):
        if self.factory.hang_connect:
            self.factory.connecting.set()
            await asyncio.Event().wait()
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False
        self.disconnected = True

    async def write_gatt_char(self, uuid, data, response):
        assert uuid == CONTROL and response
        self.writes.append(data)
        if data[:4] == b'AVH1':
            self.token = struct.unpack_from('<I', data, 4)[0]

    async def read_gatt_char(self, uuid):
        assert uuid == CONTROL
        return STATUS.pack(b'AVS1', self.token if not self.factory.busy else self.token ^ 1,
                           self.factory.mtu, int(self.callback is not None))

    async def start_notify(self, uuid, callback):
        assert uuid == AUDIO
        self.callback = callback
        self.factory.ready.set()

    async def stop_notify(self, uuid):
        self.stopped_notify = True
        self.callback = None


class Factory:
    def __init__(self, *, busy=False, mtu=185, has_service=True, hang_connect=False):
        self.clients = []
        self.ready = threading.Event()
        self.connecting = threading.Event()
        self.busy, self.mtu, self.has_service, self.hang_connect = busy, mtu, has_service, hang_connect

    def __call__(self, target, **kwargs):
        return FakeClient(self, target, **kwargs)


class TransportTests(unittest.TestCase):
    def transport(self, factory, **kwargs):
        return BleTransport('AA:BB:CC:DD:EE:FF', client_factory=factory, retry_delay=.02,
                            log=lambda _: None, **kwargs)

    def wait_until(self, predicate, transport, timeout=2):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            transport.read(4096)
            if predicate():
                return
        self.fail('Timed out waiting for fake BLE state')

    def read_data(self, transport, timeout=2):
        # Generation changes intentionally wake read() with no payload. Wait
        # for the scheduled callback rather than assuming one read receives it.
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            data = transport.read(4096)
            if data:
                return data
        self.fail('Timed out waiting for fake BLE audio')

    def test_actual_worker_fragmented_audio_heartbeat_and_clean_exit(self):
        f = Factory()
        with self.transport(f) as t:
            self.assertTrue(f.ready.wait(2))
            c = f.clients[0]
            payload = frame(1, 0) + frame(2, 1, b'a'*320) + frame(3, 2)
            for i in range(0, len(payload), 182):
                t._loop.call_soon_threadsafe(c.callback, AUDIO, payload[i:i+182])
            d = Decoder()
            output = []
            end = time.monotonic() + 2
            while not output and time.monotonic() < end:
                output += d.feed(t.read(100))
            self.assertEqual(output, [b'a'*320])
            self.assertTrue(c.kwargs['pair'])
            self.assertEqual(c.kwargs['services'], [SERVICE])
            self.assertFalse(c.kwargs['winrt']['use_cached_services'])
        self.assertFalse(t._thread.is_alive())
        self.assertTrue(c.stopped_notify and c.disconnected)
        self.assertEqual(c.writes[-1][:4], b'AVH0')

    def test_reconnect_clears_partial_take(self):
        f = Factory()
        with self.transport(f) as t:
            self.assertTrue(f.ready.wait(2))
            c = f.clients[0]
            d = Decoder()
            old_callback = c.callback
            t._loop.call_soon_threadsafe(t._loop.call_later, .02, c.callback, AUDIO,
                                        frame(1, 0) + frame(2, 1, b'a'*320))
            chunk = self.read_data(t)
            generation = t.generation
            d.feed(chunk)
            self.assertIsNotNone(d.session)
            def disconnect():
                c.is_connected = False
                c.kwargs['disconnected_callback'](c)
            t._loop.call_soon_threadsafe(disconnect)
            self.wait_until(lambda: len(f.clients) >= 2 and f.clients[-1].callback, t)
            c2 = f.clients[-1]
            t._loop.call_soon_threadsafe(old_callback, AUDIO, b'stale link data')
            payload = frame(1, 0, session=9) + frame(2, 1, b'b'*320, session=9) + frame(3, 2, session=9)
            t._loop.call_soon_threadsafe(c2.callback, AUDIO, payload)
            chunk = self.read_data(t)
            if t.generation != generation:
                d = Decoder()
            self.assertEqual(d.feed(chunk), [b'b'*320])

    def test_busy_companion_never_unsubscribes_or_releases_owner(self):
        f = Factory(busy=True)
        with self.transport(f) as t:
            self.wait_until(lambda: f.clients and f.clients[0].disconnected, t)
        c = f.clients[0]
        self.assertFalse(c.stopped_notify)
        self.assertFalse(any(x[:4] == b'AVH0' for x in c.writes))

    def test_missing_service_and_low_mtu_reject_connection(self):
        for f in (Factory(has_service=False), Factory(mtu=23)):
            with self.subTest(factory=f), self.transport(f) as t:
                self.wait_until(lambda: f.clients and f.clients[0].disconnected, t)

    def test_cancellation_during_connect_does_not_leave_worker(self):
        f = Factory(hang_connect=True)
        with self.transport(f) as t:
            self.assertTrue(f.connecting.wait(2))
        self.assertFalse(t._thread.is_alive())
        self.assertTrue(f.clients[0].disconnected)

    def test_overflow_reconnects_and_discards_old_bytes(self):
        f = Factory()
        with self.transport(f, buffer_limit=50) as t:
            self.assertTrue(f.ready.wait(2))
            c = f.clients[0]
            t._loop.call_soon_threadsafe(c.callback, AUDIO, b'x'*51)
            self.wait_until(lambda: len(f.clients) >= 2 and f.clients[-1].callback, t)
            self.assertTrue(c.disconnected)
            self.assertEqual(t.read(4096), b'')


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Windows backend only')
    async def test_paired_address_backend_does_not_require_scanning(self):
        from ble_windows import AddressWinRTClient
        from bleak import BleakClient
        client = BleakClient('AA:BB:CC:DD:EE:FF', backend=AddressWinRTClient)
        self.assertEqual(client._backend._device_info, 0xAABBCCDDEEFF)
        with self.assertRaises(ValueError):
            BleakClient('invalid', backend=AddressWinRTClient)

    async def test_paired_hid_does_not_need_advertisement(self):
        scanner = AsyncMock()
        with patch('voice_ble.paired_windows_devices', new=AsyncMock(return_value=['aa'])):
            self.assertEqual(await find_device(scanner), 'aa')
        scanner.discover.assert_not_called()

    async def test_multiple_paired_devices_require_selection(self):
        with patch('voice_ble.paired_windows_devices', new=AsyncMock(return_value=['aa', 'bb'])):
            with self.assertRaises(ConnectionError):
                await find_device(AsyncMock())


if __name__ == '__main__':
    unittest.main()
