@echo off
rem Builds dist\PartyLine.exe on Windows (needs Python 3.12 on PATH as "py").
cd /d "%~dp0"
py -3.12 -m venv .venv || goto fail
.venv\Scripts\python -m pip install --upgrade pip || goto fail
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller || goto fail
.venv\Scripts\python -m PyInstaller --noconfirm --clean PartyLine.spec || goto fail
echo.
echo Built dist\PartyLine.exe
pause
exit /b 0
:fail
echo Build failed.
pause
exit /b 1
