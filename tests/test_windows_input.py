import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import unittest
from unittest.mock import patch,Mock
import voice_companion as voice

@unittest.skipUnless(sys.platform=='win32','Windows input ABI')
class WindowsInputTests(unittest.TestCase):
    def test_unicode_without_enter(self):
        captured=[]
        def send(count,events,size):
            self.assertEqual(size,40 if sys.maxsize>2**32 else 28)
            for event in events:captured.append((event.u.ki.scan,event.u.ki.flags))
            return count
        api=Mock();api.SendInput=Mock(side_effect=send)
        with patch.object(voice,'foreground',return_value=123),patch('ctypes.WinDLL',return_value=api):
            voice.type_windows('\ud55c\uae00\ntext',123)
        self.assertEqual(captured[0],(0xd55c,4))
        self.assertTrue(all(code not in (10,13) for code,_ in captured))
        self.assertEqual([flag for _,flag in captured],[4,6]*(len(captured)//2))
    def test_focus_change_does_not_type(self):
        with patch.object(voice,'foreground',return_value=124),patch('ctypes.WinDLL') as api:
            voice.type_windows('hello',123)
            api.assert_not_called()
if __name__=='__main__':unittest.main()
