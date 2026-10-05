import sys,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from dictation_session import DictationSession

class SessionTests(unittest.TestCase):
    def setUp(self):
        self.now=0;self.log=[];self.target=(123,456)
        self.toggle=Mock(return_value=self.target)
        self.session=DictationSession(self.toggle,clock=lambda:self.now,log=self.log.append)
    def test_tail_drains_before_stop_and_targets_start_window(self):
        s=self.session;s.start();s.finish();self.now=.3
        s.tick(False);self.assertEqual(self.toggle.call_count,1)
        s.tick(True);self.toggle.assert_called_with(expected_target=self.target)
        self.assertIsNone(s.target)
    def test_focus_loss_expires_instead_of_toggling_later(self):
        s=self.session;s.start();s.finish();self.toggle.return_value=None
        self.now=.3;s.tick(True);self.assertIsNotNone(s.target)
        self.now=5.1;s.tick(True);self.assertIsNone(s.target)
        calls=self.toggle.call_count;self.now=30;s.tick(True)
        self.assertEqual(calls,self.toggle.call_count)
    def test_failed_start_never_sends_stop(self):
        self.toggle.return_value=False;s=self.session;s.start();s.finish()
        self.now=1;s.tick(True);self.assertEqual(self.toggle.call_count,1)
    def test_rapid_new_start_cancels_pending_stop(self):
        s=self.session;s.start();s.finish();s.start();self.now=1;s.tick(True)
        self.assertEqual(self.toggle.call_count,1);self.assertEqual(s.target,self.target)
        s.finish();self.now=2;s.tick(True);self.assertIsNone(s.target)
    def test_finish_does_not_extend_deadline_repeatedly(self):
        s=self.session;s.start();s.finish();self.now=4;s.finish()
        self.assertEqual(s.expires,5)

if __name__=='__main__':unittest.main()
