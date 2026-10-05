@echo off
cd /d "%~dp0"
setlocal
if not defined AHAKEY_MODEL set "AHAKEY_MODEL=large-v3-turbo"
".venv\Scripts\python.exe" -u tools\voice_companion.py --ble --language ko --type --cpu-threads 8 --model "%AHAKEY_MODEL%" %*
pause
