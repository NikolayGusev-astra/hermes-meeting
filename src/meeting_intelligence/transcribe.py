from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

from .language import _is_probably_russian_mistranscribed_as_english

log = logging.getLogger("meeting")

def _silence_speakers(segments, silence_gap: float = 1.5):
    current = 0
    previous_end = None
    out = []
    for seg in segments:
        start = float(seg["start"])
        if previous_end is not None and (start - previous_end) > silence_gap:
            current += 1
        item = dict(seg)
        item["speaker_id"] = f"SPEAKER_{current:02d}"
        out.append(item)
        previous_end = float(item["end"])
    return out


def _load_diarization_pipeline(device: str):
    """Загрузить pyannote SpeakerDiarization из бандла в репо (офлайн).

    На время загрузки ставим HF_HUB_CACHE=<repo>/models/pyannote + HF_HUB_OFFLINE=1,
    чтобы gated-модели резолвились локально (без интернета/токена), затем
    восстанавливаем env — чтобы не сломать кэш Whisper (~/.cache/huggingface).
    """
    import os
    repo_models = Path(__file__).resolve().parents[2] / "models" / "pyannote"
    saved = {k: os.environ.get(k) for k in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HUB_OFFLINE")}
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_CACHE"] = str(repo_models)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(repo_models)
    try:
        from pyannote.audio import Pipeline as _Pipeline
        pipe = _Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    try:
        import torch
        if device == "cuda" and torch.cuda.is_available():
            pipe.to(torch.device("cuda"))
    except Exception:
        pass
    return pipe


def _merge_speakers(segments, annotation, label_map=None) -> list:
    """Каждому сегменту Whisper — спикер pyannote с макс. перекрытием по времени.

    Если задан label_map (label -> имя), узнанные спикеры получают имена вместо SPEAKER_NN.
    """
    turns = list(annotation.itertracks(yield_label=True))  # (Segment, track, label)
    label_order: list = []
    for _seg, _track, label in turns:
        if label not in label_order:
            label_order.append(label)
    label_to_num = {lab: "SPEAKER_{:02d}".format(i) for i, lab in enumerate(label_order)}

    def _display(label):
        if label_map:
            nm = label_map.get(str(label))
            if nm:
                return nm
        return label_to_num.get(label, "SPEAKER_00")

    out = []
    prev = "SPEAKER_00"
    for item in segments:
        s, e = float(item["start"]), float(item["end"])
        best = None
        best_dur = 0.0
        for seg, _track, label in turns:
            osv = s if s > seg.start else seg.start
            oe = e if e < seg.end else seg.end
            dur = oe - osv
            if dur > best_dur:
                best_dur = dur
                best = label
        spk = _display(best) if best is not None else prev
        prev = spk
        new = dict(item)
        new["speaker_id"] = spk
        out.append(new)
    return out


def _wav_to_tensor(path: Path):
    """Decode wav → (mono float32 tensor[1, samples], sample_rate).

    stdlib `wave` only — обходит torchcodec (который требует FFmpeg DLL и
    падает на Windows). При необходимости ресэмплим до 16 кГц линейно.
    """
    import wave
    import numpy as np
    import torch
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sw, np.int16)
    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    data /= float(2 ** (8 * sw - 1))
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    if sr != 16000:
        n_out = int(round(data.shape[0] * 16000.0 / sr))
        # np.interp всегда возвращает float64 — pyannote требует float32
        # (иначе DoubleTensor падает на cudnn_batch_norm). См.
        # tests/unit/test_wav_to_tensor.py::test_resampled_wav_stays_float32
        data = (
            np.interp(
                np.linspace(0, data.shape[0] - 1, n_out),
                np.arange(data.shape[0]),
                data,
            )
        ).astype(np.float32)
        sr = 16000
    return torch.from_numpy(data).unsqueeze(0), sr


def _diarize_speakers(segments, audio: Path, device: str, num_speakers=None, recognize=False) -> list:
    pipe = _load_diarization_pipeline(device)
    waveform, sr = _wav_to_tensor(audio)
    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = int(num_speakers)
    result = pipe({"waveform": waveform, "sample_rate": sr}, **kwargs)
    # pyannote 4.x возвращает DiarizeOutput (.speaker_diarization); 3.x — Annotation
    annotation = getattr(result, "speaker_diarization", result)
    label_map = None
    if recognize:
        try:
            from . import voiceprints as _vp
            embs = getattr(result, "speaker_embeddings", None)
            label_map = {}
            n_hit = 0
            for label in annotation.labels():
                name = None
                vec = _vp.embedding_for_cluster(embs, label) if embs is not None else None
                if vec is not None:
                    hit = _vp.recognize(vec)
                    if hit:
                        name = hit[0]
                        n_hit += 1
                        log.info("Voice match: %s -> %s (%.2f)", label, name, hit[1])
                label_map[str(label)] = name
            log.info("Voice recognition: %d/%d speakers recognized", n_hit, len(label_map))
        except Exception as exc:
            log.warning("Voice recognition failed (%s) — keeping SPEAKER_NN labels.", exc)
            label_map = None
    return _merge_speakers(segments, annotation, label_map)


def transcribe_audio(
    audio: Path, model: str, language: Optional[str], device: str, compute_type: str,
    diarize: bool = False, num_speakers: Optional[int] = None, recognize: bool = False,
    speaker_label: Optional[str] = None,
) -> Tuple[str, dict]:
    from faster_whisper import WhisperModel

    log.info(
        "Loading whisper model=%s device=%s compute_type=%s",
        model,
        device,
        compute_type,
    )
    m = WhisperModel(model, device=device, compute_type=compute_type)
    segments_iter, info = m.transcribe(
        str(audio),
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    log.info("Detected language=%s duration=%.1fs", info.language, info.duration)
    segments = []
    for idx, seg in enumerate(segments_iter, 1):
        text = seg.text.strip()
        if not text:
            continue
        item = {
            "id": f"seg_{idx:04d}",
            "start": float(seg.start),
            "end": float(seg.end),
            "text": text,
            "speaker_id": "SPEAKER_00",
        }
        segments.append(item)
        start_min = int(seg.start // 60)
        start_sec = int(seg.start % 60)
        end_min = int(seg.end // 60)
        end_sec = int(seg.end % 60)
        item["timestamp"] = (
            f"[{start_min:02d}:{start_sec:02d}->{end_min:02d}:{end_sec:02d}]"
        )
    garbage_runs = []
    run_start = None
    for index, item in enumerate(segments):
        if len(item["text"]) <= 2:
            if run_start is None:
                run_start = index
        elif run_start is not None:
            if index - run_start >= 5:
                garbage_runs.append((run_start, index))
            run_start = None
    if run_start is not None and len(segments) - run_start >= 5:
        garbage_runs.append((run_start, len(segments)))

    if garbage_runs:
        garbage_indexes = {
            index for start, end in garbage_runs for index in range(start, end)
        }
        log.warning("Removed %d short Whisper artifact segments", len(garbage_indexes))
        segments = [
            item for index, item in enumerate(segments) if index not in garbage_indexes
        ]

    diarization_used = "silence-gap"
    if speaker_label is not None:
        # DM attribution from TG metadata — more accurate than acoustic
        # diarization, and avoids loading pyannote entirely (ADR-010 §2).
        for item in segments:
            item["speaker_id"] = str(speaker_label)
        enriched = segments
        diarization_used = "tg-sender:{}".format(speaker_label)
    elif diarize:
        try:
            enriched = _diarize_speakers(segments, audio, device, num_speakers, recognize=recognize)
            nspk = len({x["speaker_id"] for x in enriched})
            log.info("Diarization: %d speakers via pyannote", nspk)
            diarization_used = "pyannote ({:d} speakers)".format(nspk)
        except Exception as exc:
            log.warning("pyannote diarization failed (%s) — fallback to silence-gap heuristic.", exc)
            enriched = _silence_speakers(segments)
    else:
        enriched = _silence_speakers(segments)
    final_lines = []
    for item in enriched:
        final_lines.append(f"{item['timestamp']} {item['speaker_id']} | {item['text']}")
    transcript = "\n".join(final_lines)
    if _is_probably_russian_mistranscribed_as_english(transcript, info.language):
        log.warning(
            "Transcript may be Russian misdetected as English. "
            "Re-run with --language ru for better quality."
        )
    meta = {
        "schema_version": "0.1.0",
        "stt_model": model,
        "language": info.language,
        "language_probability": float(
            getattr(info, "language_probability", 0.0) or 0.0
        ),
        "no_speech_prob": float(getattr(info, "no_speech_prob", 0.0) or 0.0),
        "duration": float(info.duration),
        "segment_count": len(enriched),
        "diarization": diarization_used,
    }
    return transcript, meta

def _clean_whisper_artifacts(transcript: str) -> str:
    """Remove Whisper hallucination lines made of repeated one-character tokens."""
    clean_lines = []
    for line in transcript.splitlines():
        single_char_tokens = [token for token in line.split() if len(token) == 1]
        if (
            len(single_char_tokens) >= 4
            and len(set(single_char_tokens)) == 1
        ):
            log.warning("Removed repeated-token Whisper artifact line")
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines)
