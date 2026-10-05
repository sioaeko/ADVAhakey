"""Authenticated LAN TCP transport for AhaKey PCM; one paired device at a time."""
import hashlib
import hmac
from pathlib import Path
import secrets
import socket


def proof(token, role, nonce):
    return hmac.new(token.encode('ascii'), f'{role}:{nonce}'.encode('ascii'), hashlib.sha256).hexdigest()


def read_line(sock, limit=127):
    data=bytearray()
    while len(data)<limit:
        part=sock.recv(1)
        if not part:
            raise ConnectionError('Disconnected during pairing')
        if part==b'\n':
            return data.decode('ascii')
        data.extend(part)
    raise ValueError('Pairing line too long')


def authenticate(sock, token):
    sock.settimeout(2)
    nonce=secrets.token_hex(16)
    sock.sendall(f'AHA-CHALLENGE {nonce}\n'.encode('ascii'))
    answer=read_line(sock)
    if not hmac.compare_digest(answer, 'AHA-AUTH '+proof(token,'client',nonce)):
        raise ValueError('Pairing code mismatch')
    sock.sendall(f'AHA-OK {proof(token,"server",nonce)}\n'.encode('ascii'))
    sock.settimeout(.05)


def load_token(path):
    path=Path(path)
    try:
        with path.open('x',encoding='ascii') as file:
            file.write(secrets.token_hex(8)+'\n')
    except FileExistsError:
        pass
    token=path.read_text(encoding='ascii').strip()
    if len(token)!=16 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError('Pair code file must contain exactly 16 lowercase hex characters')
    return token


class WifiTransport:
    def __init__(self, token, host='0.0.0.0', port=7345):
        self.token,self.host,self.port=token,host,port
        self.listener=None
        self.client=None
        self.generation=0
    def __enter__(self):
        self.listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            self.listener.bind((self.host,self.port))
            self.listener.listen(1)
            self.listener.settimeout(.05)
        except BaseException:
            self.listener.close()
            raise
        return self
    def disconnect(self):
        if self.client:
            self.client.close()
            self.client=None
            self.generation+=1
    def __exit__(self,*_):
        self.disconnect()
        if self.listener:
            self.listener.close()
    def write(self,data):
        if self.client:
            try:
                self.client.sendall(data)
            except OSError:
                self.disconnect()
    def read(self,count):
        if self.client is None:
            try:
                peer,address=self.listener.accept()
            except socket.timeout:
                return b''
            try:
                authenticate(peer,self.token)
                peer.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                self.client=peer
                self.generation+=1
                print(f'Paired Cardputer connected: {address[0]}',flush=True)
            except (OSError,ValueError):
                peer.close()
                return b''
        try:
            data=self.client.recv(count)
            if not data:
                self.disconnect()
            return data
        except socket.timeout:
            return b''
        except OSError:
            self.disconnect()
            return b''
