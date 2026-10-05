"""Send the installed Codex dictation toggle only to its foreground window."""
import ctypes
from ctypes import wintypes as w

def toggle(expected_target=None):
 user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
 user.GetForegroundWindow.restype=w.HWND
 user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
 hwnd=user.GetForegroundWindow();pid=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
 kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
 kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
 kernel.CloseHandle.argtypes=[w.HANDLE]
 handle=kernel.OpenProcess(0x1000,False,pid.value)
 if not handle:return False
 try:
  name=ctypes.create_unicode_buffer(32768);size=w.DWORD(len(name))
  if not kernel.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)):return False
  target=(int(hwnd),pid.value)
  if expected_target is not None and target!=expected_target:return None
  path=name.value.lower()
  if 'openai.codex_' not in path or not path.endswith('\\chatgpt.exe'):return False
 finally:kernel.CloseHandle(handle)
 class KI(ctypes.Structure):_fields_=[('vk',w.WORD),('scan',w.WORD),('flags',w.DWORD),('time',w.DWORD),('extra',ctypes.c_size_t)]
 class MI(ctypes.Structure):_fields_=[('dx',w.LONG),('dy',w.LONG),('data',w.DWORD),('flags',w.DWORD),('time',w.DWORD),('extra',ctypes.c_size_t)]
 class U(ctypes.Union):_fields_=[('ki',KI),('mi',MI)]
 class INPUT(ctypes.Structure):_fields_=[('kind',w.DWORD),('u',U)]
 user.SendInput.argtypes=[w.UINT,ctypes.POINTER(INPUT),ctypes.c_int];user.SendInput.restype=w.UINT
 # Do not release modifiers the user is physically holding.
 if any(user.GetAsyncKeyState(k)&0x8000 for k in (0x10,0x11,0x12,0x5b,0x5c)):return False
 events=[INPUT(1,U(ki=KI(k,0,flags,0,0))) for k,flags in [(0x11,0),(0x10,0),(0x44,0),(0x44,2),(0x10,2),(0x11,2)]]
 if user.GetForegroundWindow()!=hwnd:return False
 arr=(INPUT*len(events))(*events)
 return target if user.SendInput(len(events),arr,ctypes.sizeof(INPUT))==len(events) else None
