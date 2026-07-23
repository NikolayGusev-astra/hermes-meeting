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

def transcribe_audio(
    audio: Path, model: str, language: Optional[str], device: str, compute_type: str
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
