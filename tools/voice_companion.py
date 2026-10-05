"""Cardputer ADV built-in microphone -> WAV -> local Whisper -> optional text input."""
import argparse
from datetime import datetime
from pathlib import Path
import queue
import threading
import time
import wave
from voice_protocol import Decoder

def foreground():
    import sys
    if sys.platform != 'win32':
        return None
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    return user.GetForegroundWindow()

def type_windows(text, target):
    import ctypes
    from ctypes import wintypes as w
    if not target or foreground() != target:
        print('Focus changed: transcript saved; automatic typing skipped.', flush=True)
        return
    class KI(ctypes.Structure):
        _fields_ = [('vk', w.WORD), ('scan', w.WORD), ('flags', w.DWORD), ('time', w.DWORD), ('extra', ctypes.c_size_t)]
    class MI(ctypes.Structure):
        _fields_ = [('dx', w.LONG), ('dy', w.LONG), ('data', w.DWORD), ('flags', w.DWORD), ('time', w.DWORD), ('extra', ctypes.c_size_t)]
    class U(ctypes.Union):
        _fields_ = [('ki', KI), ('mi', MI)]
    class INPUT(ctypes.Structure):
        _fields_ = [('kind', w.DWORD), ('u', U)]
    # Unicode input only, never Enter / Send. Preserve non-ASCII dictation.
    data = text.replace('\r', ' ').replace('\n', ' ').encode('utf-16-le')
    events = []
    for i in range(0, len(data), 2):
        code = int.from_bytes(data[i:i+2], 'little')
        events += [INPUT(1, U(ki=KI(0, code, 4, 0, 0))), INPUT(1, U(ki=KI(0, code, 6, 0, 0)))]
    if not events:
        return
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.SendInput.argtypes = [w.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user.SendInput.restype = w.UINT
    array = (INPUT * len(events))(*events)
    if user.SendInput(len(events), array, ctypes.sizeof(INPUT)) != len(events):
        raise RuntimeError('Windows rejected text input; transcript remains saved')
    print(f'Windows accepted {len(data)//2} UTF-16 characters for typing.', flush=True)

def save_wav(path, pcm):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    transport=parser.add_mutually_exclusive_group(required=True)
    transport.add_argument('--port', help='USB serial port')
    transport.add_argument('--wifi', action='store_true', help='Listen for paired Cardputer on LAN TCP 7345')
    transport.add_argument('--ble', action='store_true', help='Receive audio over paired Bluetooth only')
    parser.add_argument('--ble-address', help='Select a Bluetooth address when multiple ADVs are paired')
    parser.add_argument('--bind', default='0.0.0.0', help='Wi-Fi listening address')
    parser.add_argument('--token-file', type=Path, default=Path(__file__).resolve().parents[1]/'.wifi-token')
    parser.add_argument('--record-only', action='store_true', help='Save WAV without a speech model')
    parser.add_argument('--model', default='small', help='Local faster-whisper model path or model name (download on first use)')
    parser.add_argument('--language', default='ko')
    parser.add_argument('--cpu-threads', type=int, default=8, help='CPU inference threads')
    parser.add_argument('--type', action='store_true', help='Windows: type transcript into the same foreground window; never press Enter')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'recordings')
    args = parser.parse_args()
    if args.ble_address and not args.ble:
        parser.error('--ble-address requires --ble')
    import sys
    if args.type and sys.platform != 'win32':
        parser.error('--type currently supports Windows only')
    if args.ble:
        from voice_ble import BleTransport
        transport=BleTransport(args.ble_address)
    elif args.wifi:
        from voice_network import WifiTransport,load_token
        token=load_token(args.token_file)
        print(f'Cardputer pairing code: {token}',flush=True)
        print('On Cardputer: Fn+W, enter Wi-Fi credentials, this PC IPv4 and the code above.',flush=True)
        import socket
        try:
            addresses=sorted({entry[4][0] for entry in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET) if not entry[4][0].startswith('127.')})
            print('PC IPv4 candidates: '+', '.join(addresses),flush=True)
        except OSError:
            print('Use ipconfig to find this PC LAN IPv4.',flush=True)
        transport=WifiTransport(token,args.bind)
    else:
        import serial
        transport=serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=1)
        transport.port=args.port
    model = None
    if not args.record_only:
        from faster_whisper import WhisperModel
        print(f'Loading local speech model: {args.model} (CPU int8, {args.cpu_threads} threads)', flush=True)
        model = WhisperModel(args.model, device='cpu', compute_type='int8', cpu_threads=args.cpu_threads)
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = queue.Queue(maxsize=2)
    def worker():
        while True:
            item = jobs.get()
            try:
                if item is None:
                    return
                path, target = item
                segments, _ = model.transcribe(str(path), language=args.language, vad_filter=True)
                text = ''.join(part.text for part in segments).strip()
                path.with_suffix('.txt').write_text(text, encoding='utf-8')
                print(text or '[No speech detected]', flush=True)
                if args.type:
                    type_windows(text, target)
            except Exception as exc:
                print(f'Transcription error (WAV preserved): {exc}', flush=True)
            finally:
                jobs.task_done()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    target = None
    def recording_start():
        nonlocal target
        target = foreground()
        print('Recording START received', flush=True)
    def recording_end(pcm):
        if not pcm:
            return
        path = args.output / (datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.wav')
        save_wav(path, pcm)
        print(f'Saved {path.name} ({len(pcm)/32000:.2f}s)', flush=True)
        if model:
            try:
                jobs.put_nowait((path, target))
            except queue.Full:
                print('Speech queue full; WAV saved for later.', flush=True)
    def new_decoder():
        return Decoder(on_start=recording_start, on_end=recording_end,
                       on_error=lambda: print('Recording rejected: abort, CRC or sequence error', flush=True))
    decoder = new_decoder()
    last_ping = last_data = 0
    received_bytes = 0
    target = None
    try:
        if args.port:
            transport.open()
        with transport as port:
            generation=getattr(port,"generation",0)
            print('Ready. Focus your text field, then tap G0 to start and tap again to finish (Fn+Space remains hold-to-talk).', flush=True)
            while True:
                now = time.monotonic()
                if now-last_ping >= 1:
                    port.write(b'AHA-MIC\n')
                    last_ping = now
                chunk = port.read(4096)
                if getattr(port,"generation",0)!=generation:
                    if decoder.session is not None:
                        print(f"Connection changed during recording; incomplete audio discarded ({len(decoder.audio)} PCM bytes, {received_bytes} transport bytes)", flush=True)
                    received_bytes=0
                    generation=port.generation
                    decoder=new_decoder()
                    target=None
                if chunk:
                    received_bytes += len(chunk)
                    last_data = now
                    # START/END callbacks preserve per-recording focus even when a
                    # single TCP read contains the end of one take and the next start.
                    decoder.feed(chunk)
                elif decoder.session is not None and now-last_data > 3:
                    decoder=new_decoder()
                    target=None
                    print('Incomplete audio discarded: transport timeout', flush=True)
    except KeyboardInterrupt:
        print('Stopping. Finishing queued transcripts...', flush=True)
    finally:
        jobs.put(None)
        thread.join()

if __name__ == '__main__':
    main()
