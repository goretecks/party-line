"""Speech-to-text + translation with faster-whisper.

Whisper's built-in `translate` task turns any of ~100 languages into English in one pass.
"""
from __future__ import annotations

import numpy as np

# Whisper tends to hallucinate these on noise / music / gunfire.
_HALLUCINATIONS = {
    "you", "thank you.", "thanks for watching!", "thank you for watching.",
    "thanks for watching.", "bye.", "subtitles by the amara.org community",
    "please subscribe.", ".", "...",
}


class Transcriber:
    def __init__(self, model: str = "small", device: str = "auto",
                 compute_type: str = "default", task: str = "translate",
                 language: str | None = None, only_langs: list[str] | None = None,
                 min_lang_prob: float = 0.5, cpu_threads: int = 4):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(model, device=device, compute_type=compute_type,
                                  cpu_threads=cpu_threads)
        print(f"[stt] whisper '{model}' on {self.model.model.device} "
              f"({cpu_threads} CPU threads)")
        self.task = task
        self.language = language
        self.only_langs = set(only_langs or [])
        self.min_lang_prob = min_lang_prob

    def __call__(self, wav: np.ndarray) -> tuple[str, str]:
        # vad_filter runs Silero VAD (bundled with faster-whisper) to strip gunfire,
        # music, footsteps etc. before Whisper sees the clip.
        segments, info = self.model.transcribe(
            wav, task=self.task, language=self.language, beam_size=1,
            condition_on_previous_text=False, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300})
        # Language gate. `segments` is lazy: decoding only happens when iterated, so
        # rejecting here skips the expensive part for clips we don't care about.
        if self.only_langs and (info.language not in self.only_langs
                                or info.language_probability < self.min_lang_prob):
            return "", info.language
        parts = [s.text.strip() for s in segments
                 if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0]
        text = " ".join(p for p in parts if p).strip()
        if text.lower() in _HALLUCINATIONS:
            text = ""
        return text, info.language
