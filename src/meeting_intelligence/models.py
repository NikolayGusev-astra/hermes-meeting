"""Domain models for Meeting Intelligence (shared, no circular deps).

Imported by ``sources`` (Telegram refs) and ``ingest`` (grouping) so neither
module owns the dataclasses — avoids a circular import between them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional


@dataclass
class TgVoiceRef:
    """A single voice message fetched from Telegram (metadata + local file)."""

    msg_id: int
    date: datetime
    sender_label: str
    is_out: bool
    ogg_path: Path
    duration_sec: int


@dataclass
class Utterance:
    """One transcribed voice message."""

    msg_id: int
    date: datetime
    speaker: str
    audio_path: Path
    transcript: str
    meta: dict = field(default_factory=dict)


@dataclass
class Meeting:
    """A grouped session (default: one day, split on long gaps)."""

    date: date
    title: str
    utterances: list[Utterance] = field(default_factory=list)
    folder: Optional[Path] = None
