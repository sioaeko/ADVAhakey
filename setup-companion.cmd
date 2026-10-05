@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install -r tools\requirements-companion.txt
if errorlevel 1 goto fail
start "" wscript.exe "%~dp0start-companion.vbs"
exit /b 0
:fail
echo Setup failed. Install Python 3.12 and retry.
pause
exit /b 1
