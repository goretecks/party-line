@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup.bat first.
  pause
  exit /b 1
)
rem Click-through caption strip on top of the game (needs borderless/windowed mode).
.venv\Scripts\python.exe -m voip_overlay --only-lang es %*
pause
