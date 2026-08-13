"""Каталог войспринтов: регистрация голосов и авто-распознавание спикеров.

Enrollment (два способа):
  * отдельный образец:  enroll <Имя> <sample.wav>   -> compute_embedding
  * из размеченной встречи: diarize -> speaker_embeddings[K] данного спикера

Recognition: после диаризации эмбеддинг каждого кластера сравнивается (косинус)
с войспринтами; при сходстве >= threshold кластер получает имя, иначе остаётся SPEAKER_NN.

Модель эмбеддингов — wespeaker-voxceleb-resnet34-LM (256-мерные x-вектора),
из бандла models/pyannote, offline. Каталог лежит в
$HERMES_HOME/meeting-voiceprints.json (или $MEETING_VOICEPRINTS) — персональные
данные, в git не коммитятся.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import numpy as np


def _store_path() -> Path:
    override = os.environ.get("MEETING_VOICEPRINTS")
    if override:
        return Path(override)
    hh = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    return Path(hh) / "meeting-voiceprints.json"


def load_voiceprints() -> dict:
    p = _store_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def list_voiceprints() -> dict:
    return load_voiceprints()


def remove_voiceprint(name: str) -> bool:
    d = load_voiceprints()
    if name in d:
        del d[name]
        _save(d)
        return True
    return False


def _save(data: dict) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_voiceprint(name: str, embedding) -> float:
    """Сохранить войспринт (L2-норм. вектор). Возвращает норму."""
    vec = _normalize(np.asarray(embedding, dtype=np.float32).ravel())
    d = load_voiceprints()
    d[name] = [float(x) for x in vec.tolist()]
    _save(d)
    return float(np.linalg.norm(vec))


_EMB_INFERENCE = None


def _embedding_inference(device: str):
    """Inference-обёртка над wespeaker-моделью из бандла (offline). Кэшируется."""
    global _EMB_INFERENCE
    if _EMB_INFERENCE is not None:
        return _EMB_INFERENCE
    import torch
    from pyannote.audio import Model, Inference
    repo_models = Path(__file__).resolve().parents[2] / "models" / "pyannote"
    saved = {k: os.environ.get(k) for k in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HUB_OFFLINE")}
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_CACHE"] = str(repo_models)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(repo_models)
    try:
        m = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM")
        dev = torch.device("cuda" if (device == "cuda" and torch.cuda.is_available()) else "cpu")
        _EMB_INFERENCE = Inference(m, device=dev)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return _EMB_INFERENCE


def _normalize(vec: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(vec))
    return vec / n if n > 0 else vec


def compute_embedding(waveform, sample_rate: int, device: str = "cpu") -> np.ndarray:
    """Эмбеддинг 256-d (L2-норм.) из тензора/np (1, samples)."""
    import torch
    inf = _embedding_inference(device)
    if isinstance(waveform, np.ndarray):
        waveform = torch.from_numpy(np.asarray(waveform, dtype=np.float32)).unsqueeze(0)
    out = inf({"waveform": waveform, "sample_rate": sample_rate})
    data = np.asarray(out.data if hasattr(out, "data") else out, dtype=np.float32)
    vec = data.mean(axis=0) if data.ndim > 1 else data
    return _normalize(vec)


def embedding_for_cluster(speaker_embeddings, label: str) -> Optional[np.ndarray]:
    """Извлечь эмбеддинг кластера по лейблу SPEAKER_0K из массива диаризации (N,256)."""
    try:
        idx = int(str(label).split("_")[-1])
        arr = np.asarray(speaker_embeddings, dtype=np.float32)
        if arr.ndim == 2 and 0 <= idx < arr.shape[0]:
            return _normalize(arr[idx])
    except Exception:
        return None
    return None


def recognize(embedding, threshold: float = 0.5) -> Optional[tuple]:
    """Лучший матч: (name, sim) если sim >= threshold, иначе None."""
    vp = load_voiceprints()
    if not vp:
        return None
    e = _normalize(np.asarray(embedding, dtype=np.float32).ravel())
    best = None
    best_sim = threshold
    for name, vec in vp.items():
        v = _normalize(np.asarray(vec, dtype=np.float32).ravel())
        sim = float(np.dot(e, v))
        if sim >= best_sim:
            best_sim = sim
            best = name
    return (best, best_sim) if best is not None else None
