from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import contextlib
import io
import types

sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from codex_status import AppServer, clean_label, dashboard_payload, quota_windows, rollout_state, runtime_state
from companion_state import InstanceLock, read_json, write_json
from test_voice import frame


class StatusTests(unittest.TestCase):
    def test_timeout_termination_is_scoped_to_owned_process_tree(self):
        from companion_app import terminate_receiver
        from unittest.mock import Mock
        child=Mock(pid=123456);child.poll.return_value=None
        with patch('companion_app.os.name','nt'),patch('companion_app.subprocess.run') as run:
            terminate_receiver(child)
            self.assertEqual(run.call_args.args[0],['taskkill.exe','/PID','123456','/T','/F'])
        child.poll.return_value=0
        with patch('companion_app.subprocess.run') as run:
            terminate_receiver(child);run.assert_not_called()

    def test_managed_receiver_saves_only_complete_audio_and_stops(self):
        import voice_companion
        for final in (3,4):
            with self.subTest(final=final), tempfile.TemporaryDirectory() as temp:
                stop=Path(temp)/'stop';out=Path(temp)/'recordings'
                closed=[]
                class Transport:
                    generation=0
                    def __init__(self,*_,**kwargs):self.on_state=kwargs['on_state']
                    def __enter__(self):self.on_state(connected=True);return self
                    def __exit__(self,*_):closed.append(True)
                    def write(self,_):pass
                    def read(self,_):
                        stop.touch()
                        return frame(1,0)+frame(2,1,b'a'*320)+frame(final,2)
                fake=types.ModuleType('voice_ble');fake.BleTransport=Transport
                log=io.StringIO()
                argv=['voice_companion.py','--ble','--record-only','--stop-file',str(stop),'--output',str(out)]
                with patch.dict(sys.modules,{'voice_ble':fake}),patch.object(sys,'argv',argv),contextlib.redirect_stdout(log):
                    voice_companion.main()
                self.assertTrue(closed)
                self.assertEqual(len(list(out.glob('*.wav'))),int(final==3))
                self.assertIn('"state": "stopped"',log.getvalue())

    def test_unknown_quota_is_not_zero_or_unlimited(self):
        self.assertEqual(quota_windows({}),{'five_hour':None,'weekly':None})
        self.assertEqual(quota_windows({'rateLimits':{'primary':{'usedPercent':None,'windowDurationMins':300}}})['five_hour'],None)
        self.assertIsNone(quota_windows({'rateLimits':{'primary':{'usedPercent':7,'windowDurationMins':15}}})['five_hour'])

    def test_bucket_precedence_and_remaining_percent(self):
        data={'rateLimits':{'primary':{'usedPercent':99,'windowDurationMins':300}},
              'rateLimitsByLimitId':{'codex':{'primary':{'usedPercent':25,'windowDurationMins':300},
                                           'secondary':{'usedPercent':101,'windowDurationMins':10080}}}}
        self.assertEqual(quota_windows(data),{'five_hour':75,'weekly':0})
        data['rateLimitsByLimitId']={'other':{}}
        self.assertIsNone(quota_windows(data)['five_hour'])

    def test_not_loaded_does_not_mean_finished(self):
        self.assertEqual(runtime_state({'type':'notLoaded'}),'unknown')
        self.assertEqual(runtime_state({'type':'active','activeFlags':['waitingOnApproval']}),'waiting')

    def test_local_lifecycle_stale_and_response_content(self):
        now=time.time()
        def line(kind,stamp,record_type='event_msg'):
            return json.dumps({'timestamp':datetime.fromtimestamp(stamp,timezone.utc).isoformat(),
                               'type':record_type,'payload':{'type':kind}})+'\n'
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'rollout.jsonl'
            path.write_text(line('task_started',now-300),encoding='utf-8')
            self.assertEqual(rollout_state(path,now),'unknown')
            path.write_text(line('task_started',now-1)+line('task_complete',now,'response_item'),encoding='utf-8')
            self.assertEqual(rollout_state(path,now),'running')
            path.write_text(line('task_started',now-1)+line('task_complete',now),encoding='utf-8')
            self.assertEqual(rollout_state(path,now),'ready')
            path.write_text(line('task_complete',now-1)+line('user_message',now),encoding='utf-8')
            self.assertEqual(rollout_state(path,now),'unknown')
            path.write_text(line('turn_aborted',now)+'{partial',encoding='utf-8')
            self.assertEqual(rollout_state(path,now),'error')

    def test_dashboard_is_bounded_ascii_and_contains_no_title(self):
        value={'sessions':[{'state':'running','project':'프로젝트-ADV'*10,'title':'private request'}],
               'quota':{'five_hour':None,'weekly':78}}
        data=dashboard_payload(value,99)
        self.assertLessEqual(len(data),34)
        self.assertEqual(data[:5],bytes([2,255,78,1,1]))
        self.assertEqual(len(data),6+data[5])
        self.assertNotIn(b'private',data)
        self.assertTrue(all(32<=b<=126 for b in data[6:]))
        self.assertEqual(dashboard_payload({})[3:5],b'\0\0')

    def test_label_redaction(self):
        self.assertNotIn('secret123',clean_label('token=secret123'))
        self.assertNotIn('sk-1234567890',clean_label('sk-1234567890'))

    def test_atomic_runtime_and_staleness(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'status.json'
            write_json(path,{'updated':time.time(),'title':'한국어'})
            self.assertEqual(read_json(path,10)['title'],'한국어')
            write_json(path,{'updated':time.time()-20})
            self.assertEqual(read_json(path,10),{})
            path.write_text('[]')
            self.assertEqual(read_json(path),{})

    def test_instance_lock_releases_after_close(self):
        with tempfile.TemporaryDirectory() as temp:
            first=InstanceLock(Path(temp)/'lock');second=InstanceLock(Path(temp)/'lock')
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.close()
            self.assertTrue(second.acquire())
            second.close()

    def test_real_rpc_framing_and_readonly_gate(self):
        code='import sys,json\nfor line in sys.stdin:\n r=json.loads(line)\n if "id" in r: print(json.dumps({"id":r["id"],"result":{"data":[]}}),flush=True)'
        client=AppServer([sys.executable,'-u','-c',code])
        try:
            self.assertEqual(client.request('thread/list'),{'data':[]})
            with self.assertRaises(ValueError):client.request('turn/start')
        finally:
            client.close()
        self.assertIsNotNone(client.process.poll())


if __name__=='__main__':unittest.main()
