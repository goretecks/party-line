@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo   VOIP Translator - one-time setup
echo ================================================
echo.

py -3.12 --version >nul 2>nul
if errorlevel 1 goto nopython
goto havepython

:nopython
echo Python 3.12 was not found. Installing it now...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo.
  echo Could not install Python automatically.
  echo Install Python 3.12 from https://www.python.org/downloads/ then run setup.bat again.
  pause
  exit /b 1
)
echo.
echo Python installed. Close this window and double-click setup.bat again.
pause
exit /b 0

:havepython
if not exist .venv\Scripts\python.exe (
  echo Creating private Python environment in .venv ...
  py -3.12 -m venv .venv || goto fail
)
set PY=.venv\Scripts\python.exe
%PY% -m pip install --upgrade pip || goto fail
echo.
echo Installing libraries (CPU-only, ~1 GB, a few minutes)...
%PY% -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu || goto fail
%PY% -m pip install -r requirements.txt || goto fail
echo.
echo Downloading speech models (one time)...
%PY% -m voip_overlay --prefetch || goto fail
echo.
echo ================================================
echo   Setup complete! Double-click run.bat to start.
echo ================================================
pause
exit /b 0

:fail
echo.
echo Setup FAILED. Copy the error text above and send it to Claude.
pause
exit /b 1
