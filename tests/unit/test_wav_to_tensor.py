"""Offline tests for _wav_to_tensor dtype/resample behavior.

Regression: real YouTube wavs are 44.1 kHz mono; the resample branch used
``np.interp`` which silently returns float64 → pyannote got a DoubleTensor and
died with "cudnn_batch_norm ... DoubleTensor != FloatTensor" on long files
(2026-08-22, neuraldeep/2288 stream). Synthetic 16k test audio masked it.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

torch = pytest.importorskip("torch")

from meeting_intelligence.transcribe import _wav_to_tensor  # noqa: E402


def _write_wav(path: Path, samples: np.ndarray, sr: int) -> Path:
    pcm = np.clip(samples, -1.0, 1.0)
    w = wave.open(str(path), "wb")
    try:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((pcm * 32767).astype("<i2").tobytes())
    finally:
        w.close()
    return path


def test_resampled_wav_stays_float32(tmp_path):
    """Non-16kHz input must come back float32 (pyannote requires it)."""
    sr = 44100
    t = np.arange(sr * 3, dtype=np.float32) / sr
    path = _write_wav(tmp_path / "res.wav", 0.3 * np.sin(2 * np.pi * 440 * t), sr)
    wf, out_sr = _wav_to_tensor(path)
    assert out_sr == 16000
    assert wf.dtype == torch.float32, (
        "resampled waveform must stay float32, got %s" % wf.dtype
    )


def test_native_16k_wav_is_float32(tmp_path):
    """Already-16kHz file keeps float32 (existing behavior guard)."""
    sr = 16000
    t = np.arange(sr * 2, dtype=np.float32) / sr
    path = _write_wav(tmp_path / "native.wav", 0.3 * np.sin(2 * np.pi * 220 * t), sr)
    wf, out_sr = _wav_to_tensor(path)
    assert out_sr == 16000
    assert wf.dtype == torch.float32
