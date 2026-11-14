"""Online speaker identification: voiceprints + incremental clustering.

Voiceprints come from Resemblyzer's GE2E encoder (Apache-2.0), exported to ONNX by
tools/export_speaker_model.py, so only onnxruntime + numpy are needed at runtime.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np

from .audio import SAMPLE_RATE

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
_HOP, _NFFT, _PARTIAL = 160, 400, 160          # 10 ms hop, 25 ms window, 1.6 s partials


@dataclass
class Speaker:
    idx: int
    name: str
    centroid: np.ndarray = field(repr=False)
    count: int = 1


class VoiceEncoder:
    def __init__(self, threads: int = 1):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(os.path.join(ASSETS, "speaker_encoder.onnx"), so,
                                         providers=["CPUExecutionProvider"])
        self.fb = np.load(os.path.join(ASSETS, "mel_filterbank.npy"))
        n = np.arange(_NFFT)
        self.window = (0.5 - 0.5 * np.cos(2 * np.pi * n / _NFFT)).astype(np.float32)  # periodic hann

    def _mel(self, wav: np.ndarray) -> np.ndarray:
        y = np.pad(wav, _NFFT // 2)                                   # librosa center=True, constant pad
        n_frames = 1 + (len(y) - _NFFT) // _HOP
        idx = np.arange(_NFFT)[None, :] + _HOP * np.arange(n_frames)[:, None]
        spec = np.abs(np.fft.rfft(y[idx] * self.window, axis=1)) ** 2
        return (spec @ self.fb.T).astype(np.float32)                  # (frames, 40), power mel

    @staticmethod
    def _slices(n_samples: int, rate: float = 1.3, min_coverage: float = 0.75):
        n_frames = int(np.ceil((n_samples + 1) / _HOP))
        step = int(np.round((SAMPLE_RATE / rate) / _HOP))
        starts = list(range(0, max(1, n_frames - _PARTIAL + step + 1), step))
        last = starts[-1]
        coverage = (n_samples - last * _HOP) / (_PARTIAL * _HOP)
        if coverage < min_coverage and len(starts) > 1:
            starts.pop()
        return starts

    def embed(self, wav: np.ndarray) -> np.ndarray:
        wav = wav.astype(np.float32)
        rms = np.sqrt(np.mean(wav ** 2)) + 1e-9
        gain = 10 ** ((-30 - 20 * np.log10(rms)) / 20)                # normalise up to -30 dBFS
        if gain > 1:
            wav = wav * gain
        starts = self._slices(len(wav))
        need = (starts[-1] + _PARTIAL) * _HOP
        if need >= len(wav):
            wav = np.pad(wav, (0, need - len(wav)))
        mel = self._mel(wav)
        mels = np.stack([mel[s:s + _PARTIAL] for s in starts])
        partial = self.sess.run(None, {"mels": mels})[0]
        e = partial.mean(axis=0)
        return e / (np.linalg.norm(e) + 1e-9)


class SpeakerTracker:
    """Assigns each utterance to the closest known voice, or creates a new speaker."""

    def __init__(self, threshold: float = 0.84, min_new_speaker_sec: float = 1.2,
                 max_speakers: int = 12):
        self.encoder = VoiceEncoder()
        self.threshold = threshold
        self.min_new = int(min_new_speaker_sec * SAMPLE_RATE)
        self.max_speakers = max_speakers
        self.speakers: list[Speaker] = []

    def reset(self):
        self.speakers = []

    def identify(self, wav: np.ndarray) -> tuple[Speaker, bool]:
        """Returns (speaker, is_new)."""
        emb = self.encoder.embed(wav)
        long_enough = len(wav) >= self.min_new
        if self.speakers:
            sims = [float(emb @ s.centroid) for s in self.speakers]
            best = int(np.argmax(sims))
            spk = self.speakers[best]
            if sims[best] >= self.threshold:
                if long_enough:  # only refine voiceprints with reliable clips
                    w = min(spk.count, 20)
                    c = spk.centroid * w + emb
                    spk.centroid = c / np.linalg.norm(c)
                    spk.count += 1
                return spk, False
            if not long_enough or len(self.speakers) >= self.max_speakers:
                return spk, False  # too short to trust as a new voice: closest match
        spk = Speaker(len(self.speakers), f"Caller {len(self.speakers) + 1}", emb)
        self.speakers.append(spk)
        return spk, True
