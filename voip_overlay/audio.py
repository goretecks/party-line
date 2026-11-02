"""Audio sources (system loopback / wav file) and voice-activity segmentation."""
from __future__ import annotations

import queue
import threading
import time
from collections import deque

import numpy as np
import soxr
import webrtcvad

SAMPLE_RATE = 16000          # everything downstream works at 16 kHz mono float32
FRAME_MS = 30                # webrtcvad accepts 10/20/30 ms frames
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000


# --------------------------------------------------------------------------- sources

def list_output_devices() -> list[str]:
    import soundcard as sc
    return [s.name for s in sc.all_speakers()]


def _find_speaker(name: str | None):
    import soundcard as sc
    if not name:
        return sc.default_speaker()
    for spk in sc.all_speakers():
        if name.lower() in spk.name.lower():
            return spk
    raise SystemExit(f"No output device matching {name!r}. Use --list-devices.")


class LoopbackCapture(threading.Thread):
    """Records whatever is playing on an output device (WASAPI loopback on Windows,
    the PulseAudio/PipeWire monitor on Linux) and pushes 16 kHz mono chunks."""

    def __init__(self, out_q: queue.Queue, device_name: str | None = None, capture_sr: int = 48000):
        super().__init__(daemon=True, name="capture")
        self.out_q = out_q
        self.device_name = device_name
        self.capture_sr = capture_sr
        self._stop_evt = threading.Event()

    def stop(self):
        self._stop_evt.set()

    def run(self):
        import soundcard as sc
        spk = _find_speaker(self.device_name)
        mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
        print(f"[audio] capturing loopback of: {spk.name}")
        block = self.capture_sr // 10  # 100 ms
        rs = soxr.ResampleStream(self.capture_sr, SAMPLE_RATE, 1, dtype="float32")
        with mic.recorder(samplerate=self.capture_sr, blocksize=block) as rec:
            while not self._stop_evt.is_set():
                data = rec.record(numframes=block)
                mono = data.mean(axis=1) if data.ndim > 1 else data
                self.out_q.put(rs.resample_chunk(mono.astype(np.float32)))


class FileSource(threading.Thread):
    """Plays a wav/flac file into the pipeline (for testing without a game)."""

    def __init__(self, out_q: queue.Queue, path: str, realtime: bool = True):
        super().__init__(daemon=True, name="file")
        self.out_q, self.path, self.realtime = out_q, path, realtime
        self.done = threading.Event()

    def stop(self):
        pass

    def run(self):
        import soundfile as sf
        audio, sr = sf.read(self.path, dtype="float32", always_2d=True)
        audio = soxr.resample(audio.mean(axis=1), sr, SAMPLE_RATE).astype(np.float32)
        chunk = SAMPLE_RATE // 10
        for i in range(0, len(audio), chunk):
            self.out_q.put(audio[i:i + chunk])
            if self.realtime:
                time.sleep(0.1)
        self.out_q.put(np.zeros(SAMPLE_RATE * 2, np.float32))  # flush trailing utterance
        self.done.set()


# --------------------------------------------------------------------------- segmentation

class Segmenter:
    """Turns a continuous stream into utterances using WebRTC VAD.

    An utterance starts when most of the last `preroll` frames are voiced and ends
    after `end_silence_ms` of silence (or `max_ms`, so long monologues still flow).
    """

    def __init__(self, aggressiveness: int = 2, end_silence_ms: int = 600,
                 max_ms: int = 10000, min_ms: int = 400, preroll_ms: int = 300,
                 start_ratio: float = 0.6):
        self.vad = webrtcvad.Vad(aggressiveness)
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
