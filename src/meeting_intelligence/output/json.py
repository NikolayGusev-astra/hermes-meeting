from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from ..transcribe import _clean_whisper_artifacts

_SEGMENT_ID_PREFIX = re.compile(r"^\s*(?:\[?(?:seg(?:ment)?[_ -]?\d+)\]?:?\s*(?:SPEAKER_\d+\s*)?)", re.IGNORECASE)

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def prepare_agent_transcript(transcript: str, source: Path) -> dict[str, Any]:
    """Build the LLM-free cleaned transcript payload consumed by meeting agents."""
    source_lines = transcript.splitlines()
    without_artifacts = _clean_whisper_artifacts(transcript).splitlines()
    cleaned_lines = []
    segment_ids_stripped = 0
    for line in without_artifacts:
        cleaned = _SEGMENT_ID_PREFIX.sub("", line).strip()
        if cleaned != line.strip():
            segment_ids_stripped += 1
        if cleaned:
            cleaned_lines.append(cleaned)
    return {"schema_version": "0.7.1", "transcript": "\n".join(cleaned_lines), "metadata": {"source": str(source), "source_hash": _sha256(source), "input_line_count": len(source_lines), "output_line_count": len(cleaned_lines), "garbage_lines_removed": len(source_lines) - len(without_artifacts), "segment_ids_stripped": segment_ids_stripped, "llm_called": False}}
