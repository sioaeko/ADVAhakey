"""Read-only Codex observer: official App Server metadata plus local event status.

Never starts/resumes turns, installs hooks, reads auth.json, or forwards messages.
An independent App Server cannot authoritatively report another server's live
state. Recent rollout lifecycle events supply a labelled fallback; stale or
missing evidence stays unknown. Local log formats are compatibility-sensitive.
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time

STATES = {'unknown': 0, 'idle': 1, 'running': 2, 'waiting': 3, 'ready': 4, 'error': 5}
LABELS = {'unknown': '확인 불가', 'idle': '대기', 'running': '작업 중',
          'waiting': '입력 대기', 'ready': '완료', 'error': '중단 / 오류'}


def clean_label(value, limit=96):
    text = ' '.join(str(value or '').split())
    text = re.sub(r'(?i)(?:sk-[\w-]{8,}|bearer\s+\S+|(?:token|password|api[_-]?key)\s*[:=]\s*\S+)', '[redacted]', text)
    return text[:limit]


def quota_windows(result):
    """Only real 5h/7d windows get those names; null never means unlimited."""
    buckets = result.get('rateLimitsByLimitId')
    bucket = buckets.get('codex', {}) if isinstance(buckets, dict) and buckets else result.get('rateLimits', {})
    out = {'five_hour': None, 'weekly': None}
    if not isinstance(bucket, dict):
        return out
    for name in ('primary', 'secondary'):
        window = bucket.get(name)
        if not isinstance(window, dict):
            continue
        used = window.get('usedPercent')
        if isinstance(used, bool) or not isinstance(used, (int, float)) or not math.isfinite(used):
            continue
        key = {300: 'five_hour', 10080: 'weekly'}.get(window.get('windowDurationMins'))
        if key:
            out[key] = max(0, min(100, round(100 - used)))
    return out


def runtime_state(status):
    status = status if isinstance(status, dict) else {}
    kind = status.get('type')
    if kind == 'active':
        flags = status.get('activeFlags') or []
        return 'waiting' if any(f in flags for f in ('waitingOnApproval', 'waitingOnUserInput')) else 'running'
    return {'idle': 'idle', 'systemError': 'error'}.get(kind, 'unknown')


def rollout_state(path, now=None):
    """Inspect only a bounded tail and lifecycle events, not response items."""
    now = time.time() if now is None else now
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - 262144))
            if size > 262144:
                stream.readline()
            lines = stream.read(262144).splitlines()
        state, timestamp = 'unknown', 0
        for line in lines:
            if len(line) > 65536 or not re.search(rb'"type"\s*:\s*"event_msg"', line[:180]):
                continue
            try:
                record = json.loads(line)
                payload = record.get('payload', {})
                event = payload.get('type')
                if event == 'user_message':
                    state = 'unknown'  # A new prompt invalidates the previous completion.
                mapped = {'task_started': 'running', 'task_complete': 'ready',
                          'turn_aborted': 'error', 'task_failed': 'error'}.get(event)
                if mapped:
                    state = mapped
                if mapped or event in ('agent_message', 'token_count'):
                    timestamp = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00')).timestamp()
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        # A crashed process may leave task_started forever. Do not invent liveness.
        if state == 'running' and not 0 <= now - timestamp <= 180:
            state = 'unknown'
        return state
    except (OSError, ValueError):
        return 'unknown'


def codex_command():
    direct = shutil.which('codex.exe')
    if direct:
        return [direct]
    wrapper = shutil.which('codex.cmd') if os.name == 'nt' else shutil.which('codex')
    if not wrapper:
        raise FileNotFoundError('Codex CLI를 찾을 수 없습니다. Codex 설치 후 앱을 다시 여세요.')
    if os.name != 'nt':
        return [wrapper]
    # Prefer the native binary so neither PowerShell nor a visible console runs.
    base = Path(wrapper).parent / 'node_modules' / '@openai'
    matches = list(base.glob('codex*/**/codex.exe'))
    if matches:
        return [str(matches[0])]
    return [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', wrapper]


class AppServer:
    def __init__(self, command=None):
        self.process = subprocess.Popen((command or codex_command()) + ['app-server'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.responses = queue.Queue(maxsize=32)
        self.seq = 0
        threading.Thread(target=self._reader, daemon=True).start()
        try:
            self.request('initialize', {'clientInfo': {'name': 'ahakey_companion', 'version': '1.5.0'},
                                       'capabilities': {'experimentalApi': False}})
            self._send({'method': 'initialized'})
        except Exception:
            self.close()
            raise

    def _reader(self):
        try:
            while True:
                line = self.process.stdout.readline(2097153)
                if not line or len(line) > 2097152:
                    break
                try:
                    obj = json.loads(line)
                    if 'id' in obj and ('result' in obj or 'error' in obj):
                        self.responses.put(obj, timeout=1)
                except (ValueError, TypeError, queue.Full):
                    continue
        finally:
            try:
                self.responses.put_nowait({'closed': True})
            except queue.Full:
                pass

    def _send(self, value):
        self.process.stdin.write((json.dumps(value) + '\n').encode())
        self.process.stdin.flush()

    def request(self, method, params=None, timeout=10):
        if method not in ('initialize', 'thread/list', 'account/rateLimits/read'):
            raise ValueError('Observer only permits read-only metadata requests')
        self.seq += 1
        request_id = self.seq
        self._send({'id': request_id, 'method': method, 'params': params or {}})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.responses.get(timeout=max(.01, deadline - time.monotonic()))
            if response.get('closed'):
                raise ConnectionError('Codex 상태 연결이 종료됐습니다.')
            if response.get('id') != request_id:
                continue
            if 'error' in response:
                raise RuntimeError('Codex 상태 요청을 처리하지 못했습니다.')
            return response.get('result') or {}
        raise TimeoutError('Codex 상태 응답 지연')

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(3)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()


class CodexMonitor:
    def __init__(self):
        self.client = None
        self.quota = {'five_hour': None, 'weekly': None}
        self.quota_at = 0

    def snapshot(self):
        if self.client is None:
            self.client = AppServer()
        result = self.client.request('thread/list', {'limit': 8, 'sortKey': 'updated_at',
            'sourceKinds': ['cli', 'vscode', 'appServer'], 'archived': False})
        sessions = []
        for item in result.get('data', [])[:8]:
            state = runtime_state(item.get('status'))
            source = 'app-server'
            if state == 'unknown' and item.get('path'):
                state = rollout_state(item['path'])
                source = 'local-event' if state != 'unknown' else 'unknown'
            project = clean_label(str(item.get('cwd') or '').replace('\\', '/').rstrip('/').rsplit('/', 1)[-1])
            sessions.append({'id': str(item.get('id', '')), 'title': clean_label(item.get('name') or project or 'Codex'),
                             'project': project, 'state': state, 'source': source})
        if time.monotonic() - self.quota_at > 60:
            self.quota_at = time.monotonic()
            try:
                self.quota = quota_windows(self.client.request('account/rateLimits/read', timeout=5))
            except (RuntimeError, TimeoutError, queue.Empty):
                self.quota = {'five_hour': None, 'weekly': None}
        return {'updated': time.time(), 'connected': True, 'sessions': sessions, 'quota': self.quota}

    def close(self):
        if self.client:
            self.client.close()
            self.client = None


def dashboard_payload(snapshot, selected=0):
    """Six byte header plus at most 28 ASCII project characters; no prompt text."""
    sessions = snapshot.get('sessions') or []
    if not sessions:
        selected, item = 0, {}
    else:
        selected = max(0, min(int(selected), min(len(sessions), 8) - 1))
        item = sessions[selected]
    quota = snapshot.get('quota') or {}
    def percent(key):
        value = quota.get(key)
        return value if type(value) is int and 0 <= value <= 100 else 255
    label = clean_label(item.get('project') or 'Codex', 28).encode('ascii', 'replace')
    return bytes([STATES.get(item.get('state'), 0), percent('five_hour'), percent('weekly'),
                  selected + 1 if sessions else 0, min(len(sessions), 8), len(label)]) + label
