"""Entry point for both `python -m voip_translator` and the packaged .exe."""
from __future__ import annotations

import argparse
import logging
import os
import sys


def _fix_windowed_streams(log_path: str):
    # A windowed .exe has no console: sys.stdout/stderr are None and any library that
    # writes progress (e.g. model downloads) would crash. Point them at the log file.
    if sys.stdout is None or sys.stderr is None:
        f = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def main():
    from . import config
    log_path = os.path.join(config.app_dir(), "translator.log")
    _fix_windowed_streams(log_path)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"),
                  *( [logging.StreamHandler()] if sys.stderr and sys.stderr.isatty() else [])])
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    p = argparse.ArgumentParser(description="VOIP Translator")
    p.add_argument("--file", help="(testing) feed a wav file instead of live audio")
    p.add_argument("--autostart", action="store_true", help="start listening immediately")
    p.add_argument("--screenshot", help="(testing) save a screenshot after a few seconds and quit")
    p.add_argument("--demo", action="store_true", help="(testing) fill the window with sample lines")
    p.add_argument("--selftest", action="store_true", help="check every component, write to log")
    args, _ = p.parse_known_args()
    if args.selftest:
        sys.exit(_selftest())

    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("voip.translator.app")

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from .app import MainWindow, apply_style
    from .engine import Engine

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    apply_style(app)
    cfg = config.load()
    engine = Engine(cfg, test_file=args.file)
    win = MainWindow(cfg, engine)
    win.show()
    win.refresh_chips()
    if args.demo:
        _demo(win)
    if args.autostart:
        QTimer.singleShot(200, engine.start)
    if args.screenshot:
        def snap():
            win.grab().save(args.screenshot)
            app.quit()
        QTimer.singleShot(int(os.environ.get("SNAP_MS", "2500")), snap)
    sys.exit(app.exec())


def _selftest() -> int:
    """Exercise every component that doesn't need a network download."""
    import threading
    import numpy as np
    log = logging.getLogger("selftest")
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            log.info("PASS %s: %s", name, fn())
        except Exception:  # noqa: BLE001
            ok = False
            log.exception("FAIL %s", name)

    t = np.arange(48000) / 16000
    voice = (0.2 * np.sin(2 * np.pi * 160 * t) * (1 + np.sin(2 * np.pi * 4 * t))).astype(np.float32)

    def speakers():
        from .speakers import VoiceEncoder
        e = VoiceEncoder().embed(voice)
        assert e.shape == (256,) and abs(float(e @ e) - 1) < 1e-3
        return "voiceprint ok (256-d)"

    def vad():
        from .audio import Segmenter
        seg = Segmenter()
        x = np.concatenate([np.zeros(16000, np.float32), voice, np.zeros(32000, np.float32)])
        return f"{len(seg.feed(x))} utterance(s)"

    def whisper():
        import ctranslate2
        import faster_whisper
        from faster_whisper.vad import get_speech_timestamps
        get_speech_timestamps(voice)
        return f"faster-whisper {faster_whisper.__version__}, ctranslate2 {ctranslate2.__version__}, silero ok"

    def devices():
        from .audio import list_output_devices
        out = []

        def run():
            try:
                out.append(list_output_devices())
            except Exception as e:  # noqa: BLE001
                out.append(e)
        th = threading.Thread(target=run)
        th.start()
        th.join(20)
        if not out:
            raise TimeoutError("listing audio devices hung")
        if isinstance(out[0], Exception):
            raise out[0]
        return out[0] or "(no output devices found)"

    check("speaker model", speakers)
    check("voice detection", vad)
    check("whisper runtime", whisper)
    check("audio devices", devices)
    log.info("SELFTEST %s", "OK" if ok else "FAILED")
    return 0 if ok else 1


def _demo(win):
    import time
    from types import SimpleNamespace
    now = time.time()
    lines = [(0, "Caller 1", "Two on B, one of them is real low, push now!"),
             (1, "Caller 2", "Wait for me, I'm grabbing the shield first."),
             (0, "Caller 1", "The guy with the sniper is on the ridge, nobody's covering left."),
             (2, "Diego", "I've got no ammo left, can somebody drop me some light rounds?"),
             (1, "Caller 2", "Ring's closing, rotate to the building by the water."),
             (2, "Diego", "Nice one! That was clean.")]
    speakers = {}
    for i, (idx, name, text) in enumerate(lines):
        speakers[idx] = SimpleNamespace(idx=idx, name=name)
        win.on_line({"idx": idx, "name": name, "lang": "es", "text": text,
                     "time": now - (len(lines) - i) * 40, "dt": 1.2 + 0.1 * i})
    win.engine.speakers = lambda: list(speakers.values())
    win.refresh_chips()
    win.on_running(True)
    win.tach.set_live(False)  # freeze the needle for the screenshot
    win.tach.value = win.tach.target = 0.58
    win.on_status("live", "On the air — listening to Headphones (Realtek USB Audio)")


if __name__ == "__main__":
    main()
