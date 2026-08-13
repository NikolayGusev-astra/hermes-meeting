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
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np


def _store_path() -> Path:
    override = os.environ.get("MEETING_VOICEPRINTS")
    if override:
        return Path(override)
    hh = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    return Path(hh) / "meeting-voiceprints.json"


def _storage_root() -> Path:
    """Meeting artifacts root, kept in sync with the dashboard setting."""
    hermes_home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    config_path = hermes_home / "meeting-storage.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        if isinstance(config, dict) and config.get("root"):
            return Path(config["root"])
    except Exception:
        pass
    return Path(os.environ.get("MEETING_ROOT", r"C:\Work\Assist\meeting"))


def _profiles_path() -> Path:
    return _storage_root() / "speakers" / "speakers.json"


def load_profiles() -> dict:
    try:
        path = _profiles_path()
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def list_profiles() -> dict:
    return load_profiles()


def save_profile(short, full_name, role, contact, voiceprint, source_meeting="") -> None:
    profiles = load_profiles()
    profiles[str(short)] = {
        "full_name": str(full_name),
        "role": str(role),
        "contact": str(contact),
        "short": str(short),
        "voiceprint": [float(x) for x in np.asarray(voiceprint, dtype=np.float32).ravel()],
        "source_meeting": str(source_meeting),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_basename(value: str) -> str:
    safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in str(value))
    return safe.strip(".") or "speaker"


def profile_md_path(short) -> Path:
    return _storage_root() / "speakers" / f"{_safe_basename(short)}.md"


def write_profile_md(short, profile_dict) -> Path:
    profile = profile_dict or {}
    full_name = str(profile.get("full_name", short)).replace('"', r'\"')
    path = profile_md_path(short)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        "---",
        f'title: "{full_name}"',
        'tags: ["speaker", "profile"]',
        "---",
        "",
        f"- full_name: {profile.get('full_name', '')}",
        f"- должность: {profile.get('role', '')}",
        f"- contact: {profile.get('contact', '')}",
        f"- short: {profile.get('short', short)}",
        f"- source_meeting: {profile.get('source_meeting', '')}",
        f"- created_at: {profile.get('created_at', '')}",
        "",
    ]
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def sync_to_wiki(short) -> bool:
    try:
        candidates = [os.environ.get("MEETING_WIKI_DIR"), str(Path.home() / "wiki"), str(Path.home() / "llm-wiki")]
        wiki_dir = next((Path(candidate) for candidate in candidates if candidate and Path(candidate).is_dir()), None)
        if wiki_dir is None:
            return False
        import shutil
        shutil.copy2(profile_md_path(short), wiki_dir / profile_md_path(short).name)
        return True
    except Exception:
        return False


def decode_wav_mono(path) -> tuple[np.ndarray, int]:
    """Decode a PCM WAV to mono float32 and resample it to 16 kHz."""
    with wave.open(str(path), "rb") as wav:
        channels, sample_width, sample_rate, frames = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.readframes(wav.getnframes())
    if sample_width == 1:
        samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 4:
        samples = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported WAV sample width: {sample_width}")
    if channels > 1:
        samples = samples[:len(samples) // channels * channels].reshape(-1, channels).mean(axis=1)
    if sample_rate != 16000 and len(samples):
        new_length = max(1, round(len(samples) * 16000 / sample_rate))
        samples = np.interp(np.linspace(0, len(samples) - 1, new_length), np.arange(len(samples)), samples).astype(np.float32)
        sample_rate = 16000
    return samples.astype(np.float32, copy=False), sample_rate


def compute_speaker_embedding_from_audio(audio_path, device: str = "cuda") -> np.ndarray:
    samples, sample_rate = decode_wav_mono(audio_path)
    import torch
    selected_device = device
    if device == "cuda" and not torch.cuda.is_available():
        selected_device = "cpu"
    waveform = torch.from_numpy(samples).unsqueeze(0)
    return _normalize(compute_embedding(waveform, sample_rate, selected_device))


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
