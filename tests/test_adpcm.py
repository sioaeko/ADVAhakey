from pathlib import Path
import math
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
with warnings.catch_warnings():
    warnings.simplefilter('ignore', DeprecationWarning)
    import audioop  # Independent Python3.12 IMA ADPCM reference.

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
from voice_adpcm import decode_adpcm
from voice_protocol import Decoder
from test_voice import frame


class AdpcmTests(unittest.TestCase):
    def test_native_encoder_matches_independent_ima_reference(self):
        root = Path(__file__).parents[1]
        executable = Path(os.environ.get('AHAKEY_ADPCM_ENCODER', root / 'dist/adpcm_encoder.exe'))
        self.assertTrue(executable.exists(), 'Run tools/test_host.py first')
        patterns = [[0]*320, [int(20000*math.sin(i*.11)) for i in range(320)],
                    [-32768 if i%2 else 32767 for i in range(320)],
                    [i*180-28000 for i in range(320)]]
        pcm = b''.join(struct.pack('<320h', *values) for values in patterns)
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = Path(tmp)/'input.pcm', Path(tmp)/'encoded.bin'
            source.write_bytes(pcm)
            subprocess.run([str(executable), str(source), str(dest)], check=True)
            encoded = dest.read_bytes()
        self.assertEqual(len(encoded), len(patterns)*163)
        for i, values in enumerate(patterns):
            block = encoded[i*163:(i+1)*163]
            initial = (values[0], block[2])
            reference, _ = audioop.lin2adpcm(struct.pack('<320h', *(values[1:]+values[-1:])), 2, initial)
            flipped = bytearray((x>>4)|((x&15)<<4) for x in reference)
            flipped[-1] &= 15
            self.assertEqual(block[3:], flipped)
            decoded_reference, _ = audioop.adpcm2lin(reference, 2, initial)
            self.assertEqual(decode_adpcm(block), struct.pack('<h', values[0])+decoded_reference[:638])

    def test_independent_blocks_stream_as_pcm_with_sequence_checks(self):
        block = b'\0'*163
        heard = []
        decoder = Decoder(on_audio=heard.append)
        packet = frame(5, 1, block)
        self.assertEqual(len(packet), 182)
        self.assertEqual(decoder.feed(frame(1, 0)+packet+frame(3, 2)), [b'\0'*640])
        self.assertEqual(heard, [b'\0'*640])
        self.assertEqual(Decoder().feed(frame(1, 0)+frame(5, 2, block)+frame(3, 3)), [])

    def test_invalid_index_padding_and_size_are_rejected(self):
        for block in (b'\0'*162, b'\0\0\x59'+b'\0'*160, b'\0'*162+b'\x10'):
            with self.assertRaises(ValueError):
                decode_adpcm(block)
            d = Decoder()
            self.assertEqual(d.feed(frame(1, 0)+frame(5, 1, block)+frame(3, 2)), [])
            self.assertGreater(d.errors, 0)

    def test_decoded_byte_limit_checked_before_playback(self):
        heard=[]
        with patch('voice_protocol.MAX_PCM_BYTES', 320):
            d=Decoder(on_audio=heard.append)
            d.feed(frame(1, 0)+frame(5, 1, b'\0'*163))
        self.assertEqual(heard, [])
        self.assertIsNone(d.session)


if __name__ == '__main__':
    unittest.main()
