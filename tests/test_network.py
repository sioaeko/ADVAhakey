import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import socket
import threading
import tempfile
import time
import unittest
from voice_network import WifiTransport,authenticate,read_line,proof,load_token
from voice_protocol import Decoder
from test_voice import frame

TOKEN='0123456789abcdef'

def pair(client,token=TOKEN):
    client.settimeout(2)
    challenge=read_line(client)
    assert challenge.startswith('AHA-CHALLENGE ')
    nonce=challenge[14:]
    client.sendall(('AHA-AUTH '+proof(token,'client',nonce)+'\n').encode())
    answer=read_line(client)
    assert answer=='AHA-OK '+proof(token,'server',nonce)

class NetworkTests(unittest.TestCase):
    def test_tcp_audio_roundtrip_and_disconnect(self):
        with WifiTransport(TOKEN,'127.0.0.1',0) as server:
            address=server.listener.getsockname();result=[];errors=[]
            def receive():
                try:
                    decoder=Decoder();deadline=time.monotonic()+3
                    while time.monotonic()<deadline and not result:
                        result.extend(decoder.feed(server.read(71)))
                except BaseException as e:errors.append(e)
            thread=threading.Thread(target=receive);thread.start()
            with socket.create_connection(address) as client:
                pair(client)
                audio=bytes(range(160))*2
                wire=frame(1,0)+frame(2,1,audio)+frame(3,2)
                for start in range(0,len(wire),13):client.sendall(wire[start:start+13])
                thread.join(4)
                self.assertFalse(thread.is_alive());self.assertFalse(errors);self.assertEqual(result,[audio])
                before=server.generation
            server.read(1)
            self.assertGreater(server.generation,before)
    def test_bad_pair_code(self):
        left,right=socket.socketpair();errors=[]
        def server():
            try:authenticate(left,TOKEN)
            except ValueError:errors.append('rejected')
            finally:left.close()
        thread=threading.Thread(target=server);thread.start()
        try:
            nonce=read_line(right)[14:]
            right.sendall(('AHA-AUTH '+proof('ffffffffffffffff','client',nonce)+'\n').encode())
            self.assertEqual(right.recv(100),b'')
        finally:right.close();thread.join(3)
        self.assertEqual(errors,['rejected'])
    def test_token_file_is_stable_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pair';first=load_token(path)
            self.assertEqual(len(first),16);self.assertEqual(first,load_token(path))
            path.write_text('bad')
            with self.assertRaises(ValueError):load_token(path)
    def test_role_and_nonce_separation(self):
        self.assertNotEqual(proof(TOKEN,'client','a'*32),proof(TOKEN,'server','a'*32))
        self.assertNotEqual(proof(TOKEN,'client','a'*32),proof(TOKEN,'client','b'*32))
    def test_long_auth_line_rejected(self):
        left,right=socket.socketpair()
        try:
            right.sendall(b'a'*128)
            with self.assertRaises(ValueError):read_line(left)
        finally:left.close();right.close()

if __name__=='__main__':unittest.main()
