Option Explicit
Dim shell, fs, root, python, script
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
python = root & "\.venv\Scripts\pythonw.exe"
script = root & "\tools\companion_app.py"
If Not fs.FileExists(python) Then
  MsgBox "Run setup-companion.cmd once, then open this launcher again.", 48, "AhaKey Companion"
  WScript.Quit 1
End If
shell.CurrentDirectory = root
shell.Run """" & python & """ """ & script & """", 1, False
