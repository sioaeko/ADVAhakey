"""Framing shared by the USB microphone companion and its tests."""
import struct
import zlib
from voice_adpcm import decode_adpcm

HEADER = struct.Struct('<BIIH')
MAX_PCM_BYTES = 16000 * 2 * 61
class Decoder:
    def __init__(self, on_audio=None, on_start=None, on_end=None, on_error=None):
        self.on_end = on_end
        self.on_error = on_error
        self.on_start = on_start
        self.on_audio = on_audio
        self.buffer = bytearray()
        self.session = None
        self.sequence = 0
        self.audio = bytearray()
        self.starts = 0
        self.errors = 0
    def reset(self):
        self.session = None
        self.audio.clear()
    def fail(self):
        self.errors += 1
        self.reset()
        if self.on_error is not None:
            self.on_error()
    def feed(self, data):
        self.buffer.extend(data)
        complete = []
        while True:
            pos = self.buffer.find(b'AVP1')
            if pos < 0:
                self.buffer[:] = self.buffer[-3:]
                break
            del self.buffer[:pos]
            if len(self.buffer) < 15:
                break
            kind, session, seq, length = HEADER.unpack_from(self.buffer, 4)
            if length > 320 or kind not in (1, 2, 3, 4, 5):
                self.fail()
                del self.buffer[0]
                continue
            size = 19 + length
            if len(self.buffer) < size:
                break
            packet = bytes(self.buffer[:size])
            if zlib.crc32(packet[4:-4]) != struct.unpack_from('<I', packet, size-4)[0]:
                self.fail()
                # A missing BLE fragment can splice the next START into this
                # candidate. Rescan after one byte; do not consume that START.
                del self.buffer[0]
                continue
            del self.buffer[:size]
            payload = packet[15:-4]
            if kind == 1:
                self.reset()
                if seq == 0 and length == 0:
                    self.session, self.sequence = session, 1
                    self.starts += 1
                    if self.on_start is not None:
                        self.on_start()
                else:
                    self.fail()
                continue
            if self.session != session or seq != self.sequence:
                self.fail()
                continue
            self.sequence += 1
            if (kind == 2 and length == 320) or (kind == 5 and length == 163):
                if kind == 5:
                    try:
                        payload = decode_adpcm(payload)
                    except ValueError:
                        self.fail()
                        continue
                if len(self.audio) + len(payload) > MAX_PCM_BYTES:
                    self.fail()
                    continue
                self.audio.extend(payload)
                if self.on_audio is not None:
                    self.on_audio(payload)
            elif kind == 3 and length == 0:
                pcm = bytes(self.audio)
                if pcm:
                    complete.append(pcm)
                self.reset()
                if self.on_end is not None:
                    self.on_end(pcm)
            else:
                self.fail()
        return complete
