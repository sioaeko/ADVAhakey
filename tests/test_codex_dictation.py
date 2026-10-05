import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from codex_dictation import toggle

@unittest.skipUnless(sys.platform=='win32','Windows ABI')
class ToggleTests(unittest.TestCase):
    def setUp(self):
        self.hwnd=0x123456789;self.pid=57
        self.user=Mock();self.kernel=Mock()
        self.user.GetForegroundWindow.side_effect=lambda:self.hwnd
        self.user.GetAsyncKeyState.return_value=0
        self.user.GetWindowThreadProcessId.side_effect=lambda hwnd,pid:setattr(pid._obj,'value',self.pid)
        self.kernel.OpenProcess.return_value=7
        def name(handle,flags,buf,size):
            buf.value=r'C:\Program Files\WindowsApps\OpenAI.Codex_1\app\ChatGPT.exe';return True
        self.kernel.QueryFullProcessImageNameW.side_effect=name
        self.user.SendInput.side_effect=lambda count,events,size:count
        self.loader=patch('ctypes.WinDLL',side_effect=lambda name,**kw:self.user if name=='user32' else self.kernel)
        self.loader.start();self.addCleanup(self.loader.stop)
    def test_start_and_stop_match_window_and_process(self):
        target=toggle();self.assertEqual(target,(self.hwnd,self.pid))
        self.assertEqual(toggle(expected_target=target),target)
    def test_other_codex_window_not_toggled(self):
        target=toggle();self.user.SendInput.reset_mock();self.hwnd+=1
        self.assertIsNone(toggle(expected_target=target));self.user.SendInput.assert_not_called()
    def test_reused_window_from_new_process_not_toggled(self):
        target=toggle();self.user.SendInput.reset_mock();self.pid+=1
        self.assertIsNone(toggle(expected_target=target));self.user.SendInput.assert_not_called()
    def test_held_modifier_skips_injection(self):
        self.user.GetAsyncKeyState.return_value=0x8000
        self.assertFalse(toggle());self.user.SendInput.assert_not_called()
