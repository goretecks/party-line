"""One-off: convert Resemblyzer's GE2E voice encoder (Apache-2.0) to ONNX + a mel filterbank,
so the app can compute voiceprints with onnxruntime alone (no PyTorch / librosa at runtime).

    pip install resemblyzer librosa torch onnx onnxscript
    python tools/export_speaker_model.py
"""
import os
import sys
import types

sys.modules.setdefault("webrtcvad", types.ModuleType("webrtcvad"))  # resemblyzer imports it; unused here
import librosa
import numpy as np
import torch
from resemblyzer import VoiceEncoder

out = os.path.join(os.path.dirname(__file__), "..", "voip_translator", "assets")
enc = VoiceEncoder("cpu").eval()
dummy = torch.randn(2, 160, 40)
torch.onnx.export(enc, dummy, os.path.join(out, "speaker_encoder.onnx"),
                  input_names=["mels"], output_names=["embeds"],
                  dynamic_axes={"mels": {0: "batch"}, "embeds": {0: "batch"}},
                  opset_version=17, dynamo=False)
fb = librosa.filters.mel(sr=16000, n_fft=400, n_mels=40).astype(np.float32)
np.save(os.path.join(out, "mel_filterbank.npy"), fb)
print("exported", fb.shape)
