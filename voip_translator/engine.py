"""Background pipeline: capture -> segment -> (speaker id + translate) -> Qt signals.

Everything heavy runs off the GUI thread; the window only ever receives signals.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from .audio import FileSource, LoopbackCapture, Segmenter, SAMPLE_RATE

log = logging.getLogger("engine")

MODEL_SIZES = {"tiny": "75 MB", "base": "145 MB", "small": "480 MB",
               "medium": "1.5 GB", "large-v3": "3 GB"}


def friendly_error(e: Exception) -> str:
    text = f"{type(e).__name__}: {e}"
    net = ("Connect", "Proxy", "Timeout", "403", "LocalEntryNotFound", "getaddrinfo", "SSL")
    if any(n in text for n in net):
        return ("Couldn't download the speech model. Check your internet connection "
                "(only needed the first time per model), then hit START again.")
    if "out of memory" in text.lower() or "bad_alloc" in text.lower():
        return "Not enough memory for that model. Pick a smaller one."
    return f"Something went wrong: {e}  (details in the log, see Settings)"


class Engine(QObject):
    line = pyqtSignal(dict)            # {idx, name, lang, text, time, dt}
    status = pyqtSignal(str, str)      # kind: idle|busy|live|error, message
    level = pyqtSignal(float)          # 0..1 audio level for the VU meter
    running = pyqtSignal(bool)
    speakers_changed = pyqtSignal()

    def __init__(self, cfg: dict, test_file: str | None = None):
        super().__init__()
        self.cfg = cfg
        self.test_file = test_file
        self.stt = None
        self._stt_key = None
        self.tracker = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._gen = 0
        self._model_lock = threading.Lock()

    # ------------------------------------------------------------------ control (GUI thread)
    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def start(self):
        if self.is_running:
            return
        self._gen += 1
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(self._stop, self._gen),
                                        daemon=True, name="engine")
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.running.emit(False)
        self.status.emit("idle", "Off the air. Hit START when you're ready.")

    def restart(self):
        if self.is_running:
            self._stop.set()
            self.start()

    def apply_live_settings(self):
        """Settings that take effect without a restart."""
        if self.stt:
            self.stt.only_langs = {self.cfg["only_lang"]} if self.cfg["only_lang"] else set()
        if self.tracker:
            self.tracker.threshold = float(self.cfg["threshold"])

    def rename_speaker(self, idx: int, name: str):
        if self.tracker and 0 <= idx < len(self.tracker.speakers):
            self.tracker.speakers[idx].name = name
            self.speakers_changed.emit()

    def reset_speakers(self):
        if self.tracker:
            self.tracker.reset()
        self.speakers_changed.emit()

    def speakers(self):
        return list(self.tracker.speakers) if self.tracker else []

    # ------------------------------------------------------------------ worker side
    def _load_models(self, stop: threading.Event):
        from .speakers import SpeakerTracker
        from .transcriber import Transcriber
        key = (self.cfg["model"], int(self.cfg["cpu_threads"]))
        with self._model_lock:
            if self._stt_key != key:
                name = self.cfg["model"]
                self.status.emit("busy", f"Warming up the tubes… loading the {name} model. "
                                         f"First time it downloads (~{MODEL_SIZES.get(name, '?')}), "
                                         f"after that it's quick.")
                self.stt = None
                self.stt = Transcriber(name, device="cpu", compute_type="int8",
                                       task="translate", cpu_threads=key[1])
                self._stt_key = key
            if self.tracker is None:
                self.tracker = SpeakerTracker()
        self.apply_live_settings()

    def _run(self, stop: threading.Event, gen: int):
        current = lambda: gen == self._gen  # noqa: E731
        try:
            self.running.emit(True)
            self._load_models(stop)
            if stop.is_set():
                return
            audio_q: queue.Queue = queue.Queue(maxsize=300)
            seg_q: queue.Queue = queue.Queue()

            def on_error(e):
                log.exception("capture failed", exc_info=e)
                if current():
                    self.status.emit("error", f"Couldn't capture audio: {e}")
                    stop.set()
                    self.running.emit(False)

            src = (FileSource(audio_q, self.test_file, stop, on_error=on_error) if self.test_file
                   else LoopbackCapture(audio_q, self.cfg["device"] or None, stop, on_error))
            src.start()
            threading.Thread(target=self._segment_loop, args=(audio_q, seg_q, stop),
                             daemon=True, name="segment").start()
            time.sleep(0.3)
            if not stop.is_set():
                self.status.emit("live", f"On the air — listening to {src.device_label}")
            self._process_loop(seg_q, stop)
        except Exception as e:  # noqa: BLE001
            log.exception("engine failed")
            if current():
                self.status.emit("error", friendly_error(e))
        finally:
            if current():
                self.running.emit(False)
                self.level.emit(0.0)

    def _segment_loop(self, audio_q, seg_q, stop):
        seg = Segmenter()
        last_emit = 0.0
        peak = 0.0
        while not stop.is_set():
            try:
                chunk = audio_q.get(timeout=0.2)
            except queue.Empty:
                self.level.emit(0.0)
                continue
            peak = max(peak, float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0)
            now = time.monotonic()
            if now - last_emit > 0.05:
                db = 20 * np.log10(peak + 1e-9)
                self.level.emit(float(np.clip((db + 55) / 50, 0, 1)))  # -55 dB..-5 dB -> 0..1
                last_emit, peak = now, 0.0
            for utt in seg.feed(chunk):
                seg_q.put(utt)
        self.level.emit(0.0)

    def _process_loop(self, seg_q, stop):
        while not stop.is_set():
            try:
                utt = seg_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if seg_q.qsize() > 4:  # fell behind: drop stale audio rather than lag forever
                continue
            t0 = time.perf_counter()
            text, lang = self.stt(utt)
            if not text or stop.is_set():
                continue
            spk, is_new = self.tracker.identify(utt)
            dt = time.perf_counter() - t0
            log.info("%s [%s] %s (%.1fs audio, %.2fs)", spk.name, lang, text,
                     len(utt) / SAMPLE_RATE, dt)
            self.line.emit({"idx": spk.idx, "name": spk.name, "lang": lang, "text": text,
                            "time": time.time(), "dt": dt})
            if is_new:
                self.speakers_changed.emit()
