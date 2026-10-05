"""Small local IPC files. Runtime data never belongs in source control."""
import json
from pathlib import Path
import time


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def read_json(path, max_age=None):
    try:
        path = Path(path)
        if path.stat().st_size > 65536:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            return {}
        if max_age is not None and not 0 <= time.time() - float(value.get('updated', 0)) <= max_age:
            return {}
        return value
    except (OSError, ValueError, TypeError):
        return {}


class InstanceLock:
    """OS releases the advisory lock after a crash; stale files are harmless."""
    def __init__(self, path):
        self.path = Path(path)
        self.file = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('a+b')
        try:
            # Do not read a byte locked by the first process on Windows.
            self.file.seek(0, 2)
            if self.file.tell() == 0:
                self.file.write(b'0')
                self.file.flush()
            self.file.seek(0)
            import os
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self.close()
            return False

    def close(self):
        if self.file:
            self.file.close()
            self.file = None
