import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import unittest
import tempfile
import struct
import zlib
import wave
from voice_protocol import Decoder
from unittest.mock import patch
from voice_companion import save_wav

def frame(kind, seq, data=b'', session=3):
    body=struct.pack('<BIIH',kind,session,seq,len(data))+data
    return b'AVP1'+body+struct.pack('<I',zlib.crc32(body))

class VoiceTests(unittest.TestCase):
    def test_chunk_callbacks_keep_distinct_recording_targets(self):
        windows=iter([10,20]);current=[None];saved=[]
        def start():current[0]=next(windows)
        d=Decoder(on_start=start,on_end=lambda pcm:saved.append((current[0],pcm)))
        a,b=b'a'*320,b'b'*320
        d.feed(frame(1,0)+frame(2,1,a)+frame(3,2)+frame(1,0,session=4)+frame(2,1,b,session=4)+frame(3,2,session=4))
        self.assertEqual(saved,[(10,a),(20,b)])

    def test_empty_recording_still_finishes(self):
        ended=[];d=Decoder(on_end=ended.append)
        self.assertEqual(d.feed(frame(1,0)+frame(3,1)),[])
        self.assertEqual(ended,[b''])

    def test_duration_limit_checked_before_streaming(self):
        heard=[];errors=[];d=Decoder(on_audio=heard.append,on_error=lambda:errors.append(True))
        with patch('voice_protocol.MAX_PCM_BYTES',320):
            d.feed(frame(1,0)+frame(2,1,b'a'*320)+frame(2,2,b'b'*320))
        self.assertEqual(heard,[b'a'*320]);self.assertEqual(errors,[True])
        self.assertIsNone(d.session)

    def test_error_then_new_start_in_same_read(self):
        events=[];d=Decoder(on_start=lambda:events.append('start'),on_audio=lambda _:events.append('audio'),on_error=lambda:events.append('error'))
        d.feed(frame(1,0)+frame(2,7,b'a'*320)+frame(1,0)+frame(2,1,b'b'*320))
        self.assertEqual(events,['start','error','start','audio'])

    def test_invalid_start_is_reported(self):
        d=Decoder();d.feed(frame(1,8));self.assertEqual(d.errors,1)

    def test_start_callback_once_before_audio(self):
        events=[];d=Decoder(on_start=lambda:events.append('start'),on_audio=lambda _:events.append('audio'))
        data=frame(1,0)+frame(2,1,b'\0'*320)+frame(3,2)
        for byte in data:d.feed(bytes([byte]))
        self.assertEqual(events,['start','audio'])

    def test_streaming_before_end_and_reject_bad_frames(self):
        heard=[];d=Decoder(on_audio=heard.append);pcm=b'\1'*320
        self.assertEqual(d.feed(frame(1,0)+frame(2,1,pcm)),[])
        self.assertEqual(heard,[pcm])
        bad=bytearray(frame(2,2,pcm));bad[-1]^=1
        d.feed(bad);self.assertEqual(heard,[pcm])
        d.feed(frame(2,3,pcm));self.assertEqual(heard,[pcm])
        d.feed(frame(1,0)+frame(2,1,pcm)+frame(3,2))
        self.assertEqual(heard,[pcm,pcm])

    def test_fragmented_roundtrip_wav(self):
        pcm=struct.pack('<160h',*range(-80,80))
        stream=b'boot log\n'+frame(1,0)+frame(2,1,pcm)+frame(3,2)
        for chunk in (1,7,37,512):
            d=Decoder();out=[]
            for i in range(0,len(stream),chunk):out+=d.feed(stream[i:i+chunk])
            self.assertEqual(out,[pcm])
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'voice.wav';save_wav(path,out[0])
                with wave.open(str(path),'rb') as wav:
                    self.assertEqual((wav.getnchannels(),wav.getsampwidth(),wav.getframerate()),(1,2,16000))
                    self.assertEqual(wav.readframes(160),pcm)
    def test_missing_frame(self):
        d=Decoder();self.assertEqual(d.feed(frame(1,0)+frame(2,2,b'\0'*320)+frame(3,3)),[])
    def test_corrupt_frame(self):
        d=Decoder();broken=bytearray(frame(2,1,b'\0'*320));broken[50]^=1
        self.assertEqual(d.feed(frame(1,0)+broken+frame(3,2)),[])
        self.assertGreater(d.errors,0)
    def test_abort(self):
        self.assertEqual(Decoder().feed(frame(1,0)+frame(2,1,b'\0'*320)+frame(4,2)),[])
    def test_wrong_session(self):
        self.assertEqual(Decoder().feed(frame(1,0)+frame(2,1,b'\0'*320,session=4)+frame(3,2)),[])
    def test_recovery(self):
        d=Decoder();d.feed(frame(1,0)+frame(2,4,b'\0'*320))
        self.assertEqual(d.feed(frame(1,0)+frame(2,1,b'\1'*320)+frame(3,2)),[b'\1'*320])
    def test_oversize(self):
        d=Decoder();self.assertEqual(d.feed(frame(1,0)+frame(2,1,b'\0'*321)+frame(3,2)),[])
    def test_partial_end(self):
        d=Decoder();end=frame(3,2)
        self.assertEqual(d.feed(frame(1,0)+frame(2,1,b'\0'*320)+end[:-1]),[])
        self.assertEqual(d.feed(end[-1:]),[b'\0'*320])

if __name__=='__main__':unittest.main()
