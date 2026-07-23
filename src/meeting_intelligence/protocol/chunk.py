from __future__ import annotations

import logging
import os
import re
from typing import Callable, Iterable, List

log = logging.getLogger("meeting")

PROTOCOL_CHUNK_THRESHOLD_TOKENS = 6000
PROTOCOL_CHARS_PER_TOKEN = 4
PROTOCOL_SECTIONS = ("participants", "agenda", "decisions", "assignments", "open_questions", "unclear")

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()

def _protocol_chunk_size_tokens() -> int:
    value = os.getenv(
        "MEETING_PROTOCOL_CHUNK_SIZE", str(PROTOCOL_CHUNK_THRESHOLD_TOKENS)
    )
    try:
        return max(1, int(value))
    except ValueError:
        log.warning(
            "Invalid MEETING_PROTOCOL_CHUNK_SIZE=%r; using %s tokens",
            value,
            PROTOCOL_CHUNK_THRESHOLD_TOKENS,
        )
        return PROTOCOL_CHUNK_THRESHOLD_TOKENS

def _needs_protocol_chunking(transcript: str) -> bool:
    return len(transcript) > (
        PROTOCOL_CHUNK_THRESHOLD_TOKENS * PROTOCOL_CHARS_PER_TOKEN
    )

def _split_protocol_transcript(transcript: str, chunk_size_chars: int) -> List[str]:
    overlap_chars = max(1, chunk_size_chars // 10)
    chunks = []
    start = 0
    while start < len(transcript):
        end = min(len(transcript), start + chunk_size_chars)
        if end < len(transcript):
            line_end = transcript.rfind("\n", start + 1, end + 1)
            if line_end > start:
                end = line_end + 1
        chunks.append(transcript[start:end])
        if end == len(transcript):
            break
        start = max(start + 1, end - overlap_chars)
    return chunks

def _merge_protocol_chunks(protocols: Iterable[dict]) -> dict:
    merged = {section: [] for section in PROTOCOL_SECTIONS}
    seen_quotes = {section: set() for section in PROTOCOL_SECTIONS}
    for protocol in protocols:
        for section in PROTOCOL_SECTIONS:
            items = protocol.get(section, [])
            if not isinstance(items, list):
                continue
            for item in items:
                quote = (
                    _normalize(item.get("source_quote", ""))
                    if isinstance(item, dict)
                    else ""
                )
                if quote and quote in seen_quotes[section]:
                    continue
                if quote:
                    seen_quotes[section].add(quote)
                merged[section].append(item)
    return merged

def build_protocol(transcript: str, model: str, allow_cloud: bool, builder: Callable[[str, str, bool], dict] | None = None) -> dict:
    from .extract import _build_protocol_chunk

    builder = builder or _build_protocol_chunk
    if not _needs_protocol_chunking(transcript):
        return builder(transcript, model, allow_cloud)
    chunk_size_chars = _protocol_chunk_size_tokens() * PROTOCOL_CHARS_PER_TOKEN
    chunks = _split_protocol_transcript(transcript, chunk_size_chars)
    if len(chunks) == 1:
        return builder(transcript, model, allow_cloud)
    log.info("Building protocol from %s overlapping transcript chunks", len(chunks))
    return _merge_protocol_chunks(builder(chunk, model, allow_cloud) for chunk in chunks)
