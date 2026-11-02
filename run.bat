@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup.bat first.
  pause
  exit /b 1
)
rem Transcript window on monitor 2, Spanish only. Leave this black window open; close it to stop.
.venv\Scripts\python.exe -m voip_overlay --only-lang es --panel --screen 2 %*
pause
