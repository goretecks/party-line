"""Audio sources (system loopback / wav file) and voice-activity segmentation."""
from __future__ import annotations

import queue
import sys
import threading
import time
import warnings
from collections import deque

import numpy as np
import soxr

try:  # use the C extension directly: the webrtcvad wrapper imports pkg_resources,
    import _webrtcvad  # which modern Python installs no longer ship
except ImportError:  # pragma: no cover
    _webrtcvad = None

SAMPLE_RATE = 16000          # everything downstream works at 16 kHz mono float32
FRAME_MS = 30                # webrtcvad accepts 10/20/30 ms frames
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000


class _Vad:
    def __init__(self, mode: int):
        self._v = _webrtcvad.create()
        _webrtcvad.init(self._v)
        _webrtcvad.set_mode(self._v, mode)

    def is_speech(self, pcm: bytes, sr: int) -> bool:
        return _webrtcvad.process(self._v, sr, pcm, len(pcm) // 2)


# --------------------------------------------------------------------------- sources

def com_init():
    """soundcard talks to WASAPI over COM; every thread that touches it needs COM initialised.

    Order matters: soundcard calls CoInitializeEx itself on first import and treats
    "already initialised" (S_FALSE) as a fatal error, so import it *before* our own call.
    """
    import soundcard  # noqa: F401
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED; harmless if already done


def list_output_devices() -> list[str]:
    com_init()
    import soundcard as sc
    return [s.name for s in sc.all_speakers()]


def _find_speaker(name: str | None):
    import soundcard as sc
    if name:
        for spk in sc.all_speakers():
            if name.lower() in spk.name.lower():
                return spk
    return sc.default_speaker()


class LoopbackCapture(threading.Thread):
    """Records whatever is playing on an output device (WASAPI loopback on Windows,
    the PulseAudio/PipeWire monitor on Linux) and pushes 16 kHz mono chunks."""

    def __init__(self, out_q: queue.Queue, device_name: str | None, stop_evt: threading.Event,
                 on_error=None, capture_sr: int = 48000):
        super().__init__(daemon=True, name="capture")
        self.out_q, self.device_name, self.stop_evt = out_q, device_name, stop_evt
        self.on_error = on_error
        self.capture_sr = capture_sr
        self.device_label = device_name or "default output"

    def run(self):
        try:
            com_init()
            import soundcard as sc
            warnings.filterwarnings("ignore", module="soundcard")  # "data discontinuity" spam
            spk = _find_speaker(self.device_name)
            self.device_label = spk.name
            mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
            block = self.capture_sr // 10  # 100 ms
            rs = soxr.ResampleStream(self.capture_sr, SAMPLE_RATE, 1, dtype="float32")
            with mic.recorder(samplerate=self.capture_sr, blocksize=block) as rec:
                while not self.stop_evt.is_set():
                    data = rec.record(numframes=block)
                    mono = data.mean(axis=1) if data.ndim > 1 else data
                    try:
                        self.out_q.put_nowait(rs.resample_chunk(mono.astype(np.float32)))
                    except queue.Full:
                        pass
        except Exception as e:  # noqa: BLE001 - report anything to the UI
            if self.on_error:
                self.on_error(e)
            else:
                raise


class FileSource(threading.Thread):
    """Plays a wav/flac file into the pipeline (for testing without a game)."""

    def __init__(self, out_q: queue.Queue, path: str, stop_evt: threading.Event,
                 realtime: bool = True, on_error=None):
        super().__init__(daemon=True, name="file")
        self.out_q, self.path, self.realtime, self.stop_evt = out_q, path, realtime, stop_evt
        self.device_label = path

    def run(self):
        import soundfile as sf
        audio, sr = sf.read(self.path, dtype="float32", always_2d=True)
        audio = soxr.resample(audio.mean(axis=1), sr, SAMPLE_RATE).astype(np.float32)
        chunk = SAMPLE_RATE // 10
        for i in range(0, len(audio), chunk):
            if self.stop_evt.is_set():
                return
            self.out_q.put(audio[i:i + chunk])
            if self.realtime:
                time.sleep(0.1)
        self.out_q.put(np.zeros(SAMPLE_RATE * 2, np.float32))  # flush trailing utterance


# --------------------------------------------------------------------------- segmentation

class Segmenter:
    """Turns a continuous stream into utterances using WebRTC VAD.

    An utterance starts when most of the last `preroll` frames are voiced and ends
    after `end_silence_ms` of silence (or `max_ms`, so long monologues still flow).
    """

    def __init__(self, aggressiveness: int = 2, end_silence_ms: int = 600,
                 max_ms: int = 10000, min_ms: int = 400, preroll_ms: int = 300,
                 start_ratio: float = 0.6):
        self.vad = _Vad(aggressiveness)
        self.end_frames = end_silence_ms // FRAME_MS
        self.max_frames = max_ms // FRAME_MS
        self.min_samples = SAMPLE_RATE * min_ms // 1000
        self.ring: deque[tuple[np.ndarray, bool]] = deque(maxlen=preroll_ms // FRAME_MS)
        self.start_count = int(start_ratio * self.ring.maxlen)
        self.buf = np.zeros(0, np.float32)
        self.active = False
        self.frames: list[np.ndarray] = []
        self.silent = 0

    def feed(self, samples: np.ndarray) -> list[np.ndarray]:
        self.buf = np.concatenate([self.buf, samples])
        out = []
        while len(self.buf) >= FRAME_SAMPLES:
            frame, self.buf = self.buf[:FRAME_SAMPLES], self.buf[FRAME_SAMPLES:]
            pcm = (np.clip(frame, -1, 1) * 32767).astype(np.int16).tobytes()
            voiced = self.vad.is_speech(pcm, SAMPLE_RATE)
            if not self.active:
                self.ring.append((frame, voiced))
                if sum(v for _, v in self.ring) >= self.start_count:
                    self.active = True
                    self.frames = [f for f, _ in self.ring]
                    self.ring.clear()
                    self.silent = 0
                continue
            self.frames.append(frame)
            self.silent = 0 if voiced else self.silent + 1
            if self.silent >= self.end_frames or len(self.frames) >= self.max_frames:
                keep = len(self.frames) - max(0, self.silent - 5)  # trim most trailing silence
                seg = np.concatenate(self.frames[:keep])
                self.active, self.frames, self.silent = False, [], 0
                if len(seg) >= self.min_samples:
                    out.append(seg)
        return out
