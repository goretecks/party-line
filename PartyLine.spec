# PyInstaller spec: one windowed .exe, no console.   pyinstaller PartyLine.spec
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = [("voip_translator/assets", "voip_translator/assets")]
datas += collect_data_files("faster_whisper")      # bundled Silero VAD model
datas += collect_data_files("soundcard")           # WASAPI cffi headers
binaries = collect_dynamic_libs("ctranslate2")

a = Analysis(
    ["tools/launch.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=["_webrtcvad"],
    excludes=["tkinter", "torch", "matplotlib", "pandas", "scipy", "IPython",
              "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtPdf", "PyQt6.QtNetwork",
              "PyQt6.QtOpenGL", "PyQt6.QtMultimedia", "PyQt6.QtWebEngineCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="PartyLine",
    icon="voip_translator/assets/icon.ico",
    console=False,          # no black cmd window
    upx=False,
    runtime_tmpdir=None,
)
