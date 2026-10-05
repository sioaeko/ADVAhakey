"""Paired ADV Wi-Fi/Bluetooth PCM -> explicitly selected VB-CABLE endpoint."""
import argparse, threading, time
from pathlib import Path
import numpy as np
import sounddevice as sd
from voice_network import WifiTransport, load_token
from voice_protocol import Decoder
from codex_dictation import toggle
from dictation_session import DictationSession

def main():
 p=argparse.ArgumentParser();p.add_argument('--list',action='store_true');p.add_argument('--device',type=int)
 p.add_argument('--ble',action='store_true',help='Use paired Bluetooth instead of Wi-Fi');p.add_argument('--ble-address');a=p.parse_args()
 if a.ble_address and not a.ble:p.error('--ble-address requires --ble')
 if a.list:print(sd.query_devices());return
 if a.device is None:
  choices=[i for i,d in enumerate(sd.query_devices()) if 'CABLE Input' in d['name'] and d['max_output_channels'] and sd.query_hostapis(d['hostapi'])['name']=='Windows WASAPI']
  if len(choices)!=1:p.error('Install VB-CABLE or select its playback device with --device; use --list')
  a.device=choices[0]
 device=sd.query_devices(a.device)
 if 'CABLE Input' not in device['name'] or not device['max_output_channels']:p.error('Select the VB-CABLE CABLE Input playback endpoint')
 rate=48000;channels=min(2,device['max_output_channels']);buf=bytearray();lock=threading.Lock();stats={'bytes':0,'dropped':0}
 session=DictationSession(toggle, log=lambda message: print(message,flush=True))
 def start():
  session.start()
  print('Recording START',flush=True)
 def finish(pcm):
  session.finish()
  print('Recording END; PCM bytes='+str(len(pcm)),flush=True)
 def invalid():
  with lock:buf.clear()
  session.finish()
  print('Invalid audio discarded',flush=True)
 def new_decoder():
  return Decoder(on_audio=receive,on_start=start,on_end=finish,on_error=invalid)
 def receive(pcm):
  # Exact 3x sample repetition converts 16 kHz mono to 48 kHz; no word processing.
  x=np.repeat(np.frombuffer(pcm,dtype='<i2'),3)
  if channels==2:x=np.repeat(x[:,None],2,axis=1)
  data=x.tobytes()
  with lock:
   if len(buf)+len(data)>rate*channels*2:stats['dropped']+=len(buf);buf.clear()
   buf.extend(data);stats['bytes']+=len(pcm)
 def render(out,frames,info,status):
  n=frames*channels*2
  with lock:
   if time.monotonic()<session.ready:data=b''
   else:data=bytes(buf[:n]);del buf[:n]
  out[:]=data+b'\0'*(n-len(data))
 if a.ble:
  from voice_ble import BleTransport
  transport=BleTransport(a.ble_address)
 else:
  token=load_token(Path(__file__).resolve().parents[1]/'.wifi-token');transport=WifiTransport(token)
 decoder=new_decoder()
 with sd.RawOutputStream(device=a.device,samplerate=rate,channels=channels,dtype='int16',blocksize=480,callback=render),transport as port:
  generation=port.generation;ping=0;last=0
  print('Audio bridge ready: '+device['name'],flush=True)
  while True:
   now=time.monotonic()
   with lock:drained=not buf
   session.tick(drained)
   if now-ping>=1:port.write(b'AHA-MIC\n');ping=now
   chunk=port.read(4096)
   if port.generation!=generation:
    session.finish()
    generation=port.generation;decoder=new_decoder()
    with lock:buf.clear()
   if chunk:
    decoder.feed(chunk)
    last=now
   elif decoder.session is not None and now-last>3:
    decoder=new_decoder()
    with lock:buf.clear()
    session.finish()
    print('Recording timeout',flush=True)
if __name__=='__main__':main()
