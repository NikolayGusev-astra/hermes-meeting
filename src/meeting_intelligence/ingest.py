"""Telegram voice ingest — grouping into meetings (ADR-010 / SDD v0.9.0).

Turns downloaded Telegram voice refs into ``Meeting`` objects grouped by day
(with a gap-based split inside a day), then drives transcription per utterance.
Speaker attribution for DMs comes from TG metadata (``TgVoiceRef.sender_label``),
NOT acoustic diarization.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

from .models import Meeting, TgVoiceRef, Utterance

log = logging.getLogger("meeting")

GAP_MINUTES = 120  # split a day into separate meetings if gap exceeds this


def group_into_meetings(
    refs: list[TgVoiceRef], gap_minutes: int = GAP_MINUTES
) -> list[Meeting]:
    """Group voice refs into meetings.

    Day is the base boundary. Inside a day, a gap larger than ``gap_minutes``
    starts a new meeting. Refs are sorted by date ascending. Each meeting's
    ``utterances`` are pre-populated (empty transcript); ``ingest_telegram``
    fills the transcript in.
    """
    if not refs:
        return []
    ordered = sorted(refs, key=lambda r: r.date)
    meetings: list[Meeting] = []
    current: list[TgVoiceRef] = []
    prev: Optional[datetime] = None
    cur_day: Optional[date] = None

    def flush():
        if current:
            day = cur_day or current[0].date.date()
            m = Meeting(date=day, title="", utterances=[], folder=None)
            m.utterances = [
                Utterance(
                    msg_id=r.msg_id,
                    date=r.date,
                    speaker=r.sender_label,
                    audio_path=r.ogg_path,
                    transcript="",
                )
                for r in current
            ]
            meetings.append(m)

    for ref in ordered:
        ref_day = ref.date.date()
        if prev is not None:
            gap = (ref.date - prev).total_seconds() / 60.0
            day_changed = ref_day != cur_day
            if day_changed or gap > gap_minutes:
                flush()
                current = []
        current.append(ref)
        cur_day = ref_day
        prev = ref.date
    flush()
    return meetings


def _title_from_utterances(utterances: list[Utterance]) -> str:
    """Derive a short topic for the meeting folder name (NAMING.md style)."""
    if not utterances:
        return "встреча"
    words = utterances[0].transcript.replace(".", " ").split()
    words = [w for w in words if len(w) > 2][:3]
    return "-".join(words) if words else "встреча"


def ingest_telegram(
    handle: str,
    since: Optional[str] = None,
    limit: int = 3000,
    language: str = "ru",
    device: str = "cuda",
    compute_type: str = "float16",
    output_dir: Optional[Path] = None,
    model: str = "large-v3-turbo",
) -> list[Meeting]:
    """Full pipeline: fetch TG voices -> transcribe each -> group into meetings.

    Returns ``Meeting`` objects with populated ``utterances`` and ``folder``
    (written to disk following NAMING.md). No LLM protocol step here — that is
    optional via the agent path.
    """
    from .sources import resolve_tg_source
    from .transcribe import transcribe_audio

    out = Path(output_dir) if output_dir else Path.cwd()
    refs = resolve_tg_source(handle, since=since, limit=limit, output_dir=out)
    if not refs:
        log.info("No voice messages found for %s", handle)
        return []

    # Transcribe each ref
    utt_by_ref: dict[int, Utterance] = {}
    for ref in refs:
        transcript, meta = transcribe_audio(
            ref.ogg_path,
            model,
            language,
            device,
            compute_type,
            speaker_label=ref.sender_label,
        )
        utt_by_ref[ref.msg_id] = Utterance(
            msg_id=ref.msg_id,
            date=ref.date,
            speaker=ref.sender_label,
            audio_path=ref.ogg_path,
            transcript=transcript,
            meta=meta,
        )

    meetings = group_into_meetings(refs)
    for m in meetings:
        m.title = _title_from_utterances(m.utterances)
        folder = out / f"{m.date.strftime('%Y-%m-%d')}_встреча_{m.title}"
        folder.mkdir(parents=True, exist_ok=True)
        m.folder = folder
        # Per-utterance transcript files
        for u in m.utterances:
            u.transcript = utt_by_ref[u.msg_id].transcript
            u.meta = utt_by_ref[u.msg_id].meta
            (folder / f"{u.date.strftime('%H%M%S')}.transcript.txt").write_text(
                u.transcript, encoding="utf-8"
            )
        # Summary file grouped by meeting
        summary = "\n\n".join(
            f"**{u.date.strftime('%H:%M:%S')}** ({u.speaker}):\n{u.transcript}"
            for u in m.utterances
        )
        (folder / "Сводный_транскрипт.md").write_text(summary, encoding="utf-8")
        log.info("Meeting %s: %d utterances -> %s", m.date, len(m.utterances), folder)
    return meetings
