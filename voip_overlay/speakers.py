"""Online speaker identification: voice embeddings + incremental clustering.

Each utterance is turned into a 192-d ECAPA voice embedding. It's assigned to the
closest known speaker if similar enough, otherwise it becomes a new speaker.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from .audio import SAMPLE_RATE


@dataclass
class Speaker:
    idx: int
    name: str
    centroid: np.ndarray
    count: int = 1


class SpeakerTracker:
    def __init__(self, threshold: float = 0.45, names: list[str] | None = None,
                 min_new_speaker_sec: float = 1.2, max_speakers: int = 10,
                 device: str = "cpu"):
        import torch
        from speechbrain.inference.speaker import EncoderClassifier
        from speechbrain.utils.fetching import LocalStrategy

        torch.set_num_threads(2)  # tiny model; don't compete with the game for CPU
        self.torch = torch
        save = os.path.join(os.path.expanduser("~"), ".cache", "voip-overlay", "ecapa")
        self.model = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb", savedir=save,
            run_opts={"device": device},
            local_strategy=LocalStrategy.COPY)  # default SYMLINK needs admin on Windows
        self.threshold = threshold
        self.names = names or []
        self.min_new = int(min_new_speaker_sec * SAMPLE_RATE)
        self.max_speakers = max_speakers
        self.speakers: list[Speaker] = []
        self.last: Speaker | None = None

    def _embed(self, wav: np.ndarray) -> np.ndarray:
        with self.torch.no_grad():
            emb = self.model.encode_batch(self.torch.from_numpy(wav)[None])
        v = emb.squeeze().cpu().numpy().astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    def _new(self, emb: np.ndarray) -> Speaker:
        i = len(self.speakers)
        name = self.names[i] if i < len(self.names) else f"Speaker {i + 1}"
        spk = Speaker(i, name, emb)
        self.speakers.append(spk)
        return spk

    def identify(self, wav: np.ndarray) -> Speaker:
        emb = self._embed(wav)
        if not self.speakers:
            self.last = self._new(emb)
            return self.last

        sims = [float(emb @ s.centroid) for s in self.speakers]
        best = int(np.argmax(sims))
        spk = self.speakers[best]
        long_enough = len(wav) >= self.min_new

        if sims[best] >= self.threshold:
            if long_enough:  # only refine the voiceprint with reliable clips
                w = min(spk.count, 20)  # cap so the voiceprint can still adapt
                c = spk.centroid * w + emb
                spk.centroid = c / np.linalg.norm(c)
                spk.count += 1
        elif long_enough and len(self.speakers) < self.max_speakers:
            spk = self._new(emb)
        # else: short/ambiguous clip -> fall back to the closest known speaker

        self.last = spk
        return spk
