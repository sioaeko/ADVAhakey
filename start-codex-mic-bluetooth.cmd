@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -u tools\voice_audio_bridge.py --ble %*
pause
