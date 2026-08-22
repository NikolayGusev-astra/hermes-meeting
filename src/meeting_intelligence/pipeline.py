"""Typed pipeline API for meeting intelligence orchestration.

Single source of truth for the processing pipeline. CLI, Hermes plugin,
MCP server, and web dashboard all delegate here.

See: docs/adr/007-pipeline-api-extraction.md
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional
from urllib.parse import urlparse

from tenacity import retry, stop_after_attempt, wait_exponential

from .attribution import attribute_speakers
from .gpu import _transcribe_default_device
from .output import prepare_agent_transcript, write_protocol_docx
from .output.docx import NAMES_RU
from .protocol import _build_protocol_chunk, _protocol_verification_enabled, _verify_protocol
from .protocol import chunk as _protocol_chunk
from .protocol.chunk import _needs_protocol_chunking
from .sources import (
    MeetingError,
    _is_tg_source,
    _is_url,
    _parse_tg_post,
    _resolve_source,
    fail,
    resolve_tg_post_media,
    resolve_tg_source,
)  # noqa: F401
from .transcribe import _clean_whisper_artifacts, transcribe_audio  # noqa: F401
from .vision import describe_image  # noqa: F401

log = logging.getLogger("meeting")

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# ── Configuration constants ──────────────────────────────────────────────

MAX_FILE_MB = int(os.getenv("MEETING_MAX_FILE_MB", "2048"))
MAX_DURATION_SEC = int(os.getenv("MEETING_MAX_DURATION_SEC", "7200"))

TRANSCRIBE_MODEL = os.getenv("MEETING_TRANSCRIBE_MODEL") or (
    "large-v3-turbo" if _transcribe_default_device() == "cuda" else "small"
)
TRANSCRIBE_DEVICE = os.getenv("MEETING_TRANSCRIBE_DEVICE") or _transcribe_default_device()
TRANSCRIBE_COMPUTE = os.getenv("MEETING_TRANSCRIBE_COMPUTE") or (
    "float16" if TRANSCRIBE_DEVICE == "cuda" else "int8"
)
TRANSCRIBE_LANG = os.getenv("MEETING_TRANSCRIBE_LANG", "en")
LLM_BASE_URL = os.getenv("MEETING_LLM_BASE_URL", "http://localhost:1234/v1")
LLM_API_KEY = os.getenv("MEETING_LLM_API_KEY", "lm-studio")
LLM_MODEL = os.getenv("MEETING_LLM_MODEL", "qwen2.5-7b-instruct")
TRANSLATE_BATCH_SIZE = int(os.getenv("MEETING_TRANSLATE_BATCH_SIZE", "8"))


# ── Utility functions ────────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def is_loopback_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1", ""}


def enforce_cloud_policy(allow_cloud: bool) -> None:
    if not allow_cloud and not is_loopback_url(LLM_BASE_URL):
        fail(
            f"Cloud LLM is disabled; external URL {LLM_BASE_URL!r}. "
            f"Pass --allow-cloud explicitly."
        )


def _handle_exception(exc: Exception) -> None:
    msg = str(exc)
    log.error("Meeting pipeline error: %s", msg)
    raise MeetingError(msg) from exc


# ── Resource limits & audio extraction ───────────────────────────────────


def _probe_duration(path: Path) -> float:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_format", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise MeetingError(f"ffprobe failed: {proc.stderr[-200:]}")
        payload = json.loads(proc.stdout or "{}")
        duration = payload.get("format", {}).get("duration")
        if duration is None:
            raise MeetingError("ffprobe did not return duration")
        return float(duration)
    except Exception as exc:
        raise MeetingError(f"Duration probe failed: {exc}") from exc


def check_resource_limits(
    path: Path,
    *,
    max_file_mb: Optional[int] = None,
    max_duration_sec: Optional[int] = None,
) -> None:
    size_mb = path.stat().st_size / (1024 * 1024)
    if max_file_mb is None:
        max_file_mb = int(os.getenv("MEETING_MAX_FILE_MB", "2048"))
    if max_duration_sec is None:
        max_duration_sec = int(os.getenv("MEETING_MAX_DURATION_SEC", "7200"))
    if size_mb > max_file_mb:
        fail(f"File too large: {size_mb:.1f} MB > {max_file_mb} MB")
    duration = _probe_duration(path)
    if duration > max_duration_sec:
        fail(f"Duration too long: {duration:.0f}s > {max_duration_sec}s")


def extract_audio(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(dst),
    ]
    log.info("Extracting audio -> %s", dst)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    if res.returncode != 0:
        fail(f"ffmpeg failed: {res.stderr[-400:]}")
    if not dst.exists() or dst.stat().st_size == 0:
        fail("ffmpeg produced empty audio file")
    return dst


# ── Protocol helpers ─────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _participant_map(value: Optional[str]) -> dict[str, str]:
    if not value:
        return {}
    return {
        speaker.strip(): name.strip()
        for pair in value.split(",")
        for speaker, name in [pair.strip().split("=", 1)]
    }


def replace_participant_labels(protocol: dict, participants: Optional[str]) -> None:
    apply_speaker_mapping(protocol, _participant_map(participants))


def apply_speaker_mapping(protocol: dict, mapping: dict[str, str]) -> None:
    """Apply a SPEAKER_NN-to-name mapping to protocol people fields."""
    for section in ["participants", "decisions", "assignments"]:
        for item in protocol.get(section, []):
            if not isinstance(item, dict):
                continue
            for field_name in ["name", "assignee", "approved_by"]:
                value = item.get(field_name)
                if isinstance(value, str) and value in mapping:
                    item[field_name] = mapping[value]
                elif isinstance(value, list):
                    item[field_name] = [mapping.get(entry, entry) for entry in value]


def validate_protocol(protocol: Optional[dict], transcript: str) -> dict:
    if not protocol:
        return {
            "valid": False,
            "errors": ["protocol is empty"],
            "warnings": [],
            "overall_confidence": 0,
        }
    errors: List[str] = []
    warnings: List[str] = []
    transcript_norm = _normalize(transcript)
    for section in ["assignments", "decisions", "participants"]:
        for item in protocol.get(section, []):
            if isinstance(item, str):
                errors.append(f"{section} item is plain string, expected dict: {item[:80]}")
                continue
            sq = (item.get("source_quote") or "").strip()
            if not sq:
                errors.append(f"{section} item missing source_quote: {str(item)[:80]}")
                continue
            sq_norm = _normalize(sq)
            sq_words = [w for w in sq_norm.split() if len(w) > 2]
            if sq_words:
                found = sum(1 for w in sq_words if w in transcript_norm)
                if found < max(1, len(sq_words) * 0.6):
                    errors.append(f"{section} source_quote not found: {sq[:80]}")
            assignee = (item.get("assignee") or "").strip()
            if assignee and assignee != "unknown":
                if assignee.lower() not in transcript_norm:
                    warnings.append(f"{section} assignee may be transliterated: {assignee}")
            deadline = (item.get("deadline") or "").strip()
            if deadline and deadline != "not_set":
                if not re.search(
                    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
                    r"|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
                    r"|\d{1,2}[./:]\d{1,2}[./:]\d{2,4}|tmr|tomorrow|week|month|q[1-4])",
                    deadline,
                    re.I,
                ):
                    warnings.append(f"{section} deadline may be fabricated: {deadline}")
    confidence = 90
    if errors:
        confidence = min(confidence, 25)
    elif warnings:
        confidence = min(confidence, 70)
    return {
        "valid": len(errors) == 0,
        "errors": errors[:20],
        "warnings": warnings[:10],
        "overall_confidence": confidence,
    }


def build_protocol(
    transcript: str, model: str, allow_cloud: bool, *, auto_attribute: bool = True
) -> dict:
    """Build a protocol while retaining the legacy CLI monkeypatch seam."""
    protocol = _protocol_chunk.build_protocol(
        transcript, model, allow_cloud, builder=_build_protocol_chunk
    )
    participants = protocol.get("participants", [])
    participant_names = [
        item.get("name")
        for item in participants
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    if (
        auto_attribute
        and participant_names
        and all(re.fullmatch(r"SPEAKER_\d+", name) for name in participant_names)
    ):
        result = attribute_speakers(transcript, model, allow_cloud)
        if result["ok"] and result["mapping"]:
            apply_speaker_mapping(protocol, result["mapping"])
            log.info("Applied automatic speaker attribution: %s", result["mapping"])
        elif not result["ok"]:
            log.warning("Automatic speaker attribution failed: %s", result["err"])
    return protocol


# ── Translation ──────────────────────────────────────────────────────────


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _translate_one(client: Any, text: str, target_lang: str) -> str:
    prompt = (
        f"Translate to {target_lang}. Keep names/codes/technical terms unchanged. "
        f"Output ONLY translation, no extra text.\n\n{text}"
    )
    return (
        client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        .choices[0]
        .message.content.strip()
    )


def _chunked(seq: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def translate_lines(lines: List[str], target_lang: str, allow_cloud: bool) -> List[str]:
    enforce_cloud_policy(allow_cloud)
    if not lines:
        return []
    from openai import OpenAI

    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    out: List[str] = []
    failed = 0
    head_pat = re.compile(
        r"^\[(\d{2}:\d{2})->(\d{2}:\d{2})\]\s+(SPEAKER_\d+)\s+\|\s+(.*)$"
    )
    chunk_buf: List[str] = []
    prefix_buf: List[str] = []
    for line in lines:
        m = head_pat.match(line)
        if m:
            prefix_buf.append(f"[{m.group(1)}->{m.group(2)}] {m.group(3)} | ")
            chunk_buf.append(m.group(4))
        else:
            prefix_buf.append("")
            chunk_buf.append(line)
        if len(chunk_buf) >= TRANSLATE_BATCH_SIZE:
            try:
                translated = _translate_one(client, "\n".join(chunk_buf), target_lang)
                parts = translated.splitlines()
                if len(parts) != len(chunk_buf):
                    raise ValueError("Translator returned wrong line count")
                out.extend(
                    f"{p}{part}"
                    for p, part in zip(prefix_buf[-len(chunk_buf) :], parts)
                )
            except Exception as exc:
                failed += len(chunk_buf)
                log.warning("Batch translate failed: %s", exc)
            finally:
                chunk_buf.clear()
                prefix_buf.clear()
    if chunk_buf:
        try:
            translated = _translate_one(client, "\n".join(chunk_buf), target_lang)
            parts = translated.splitlines()
            if len(parts) != len(chunk_buf):
                raise ValueError("Translator returned wrong line count")
            out.extend(f"{p}{part}" for p, part in zip(prefix_buf, parts))
        except Exception as exc:
            failed += len(chunk_buf)
            log.warning("Batch translate failed: %s", exc)
    if failed:
        fail(f"LLM translation failed for {failed} line(s)")
    return out


# ── Typed params & results (domain model) ────────────────────────────────


@dataclass
class TranscribeParams:
    source: str
    model: str = "small"
    language: str = "en"
    device: str = "cpu"
    compute_type: str = "int8"
    output: Optional[Path] = None
    diarize: bool = False
    num_speakers: Optional[int] = None
    recognize: bool = False
    speaker_label: Optional[str] = None
    tg_since: Optional[str] = None
    tg_limit: int = 3000
    max_duration_sec: Optional[int] = None
    max_file_mb: Optional[int] = None


@dataclass
class TranscribeResult:
    transcript_path: Path
    transcript: str
    meta: dict


@dataclass
class TranslateParams:
    transcript: Path
    target_lang: str = "ru"
    allow_cloud: bool = False
    output: Optional[Path] = None


@dataclass
class TranslateResult:
    output_path: Path
    lines: List[str]


@dataclass
class ProtocolParams:
    transcript: Path
    model: str = "qwen2.5-7b-instruct"
    allow_cloud: bool = False
    docx: bool = False
    participants: Optional[str] = None
    output: Optional[Path] = None


@dataclass
class ProtocolResult:
    protocol_path: Optional[Path]
    protocol: dict
    validation: dict
    valid: bool


@dataclass
class ProcessParams:
    source: str
    stt_model: str = "small"
    llm_model: str = "qwen2.5-7b-instruct"
    language: str = "en"
    device: str = "cpu"
    compute_type: str = "int8"
    target_lang: str = "ru"
    skip_translate: bool = False
    docx: bool = False
    allow_cloud: bool = False
    participants: Optional[str] = None
    diarize: bool = False
    num_speakers: Optional[int] = None
    recognize: bool = False
    max_duration_sec: Optional[int] = None
    max_file_mb: Optional[int] = None


@dataclass
class ProcessResult:
    transcript_path: Path
    transcript: str
    translated_path: Optional[Path]
    protocol_path: Optional[Path]
    protocol: dict
    valid: bool


# ── Orchestration functions ──────────────────────────────────────────────


def transcribe(params: TranscribeParams) -> TranscribeResult:
    """Resolve source, transcribe audio, clean artifacts, save transcript.

    When ``source`` is a Telegram handle/link (``tg:`` or ``t.me/...``), the
    full ingest pipeline runs: fetch voices via userbot → transcribe each with
    DM speaker attribution → group into meetings (ADR-010). The first meeting's
    folder is returned as ``transcript_path`` for backward-compatible callers.
    """
    parsed_post = _parse_tg_post(params.source)
    if parsed_post is not None:
        # ADR-011: конкретный пост → медиа-вложение → файловая ветка
        import tempfile as _tempfile

        channel, post_id = parsed_post
        out_dir = (
            params.output.parent
            if params.output
            else Path(_tempfile.mkdtemp(prefix="meeting-tg-post-"))
        )
        src = resolve_tg_post_media(channel, post_id, output_dir=out_dir)
    elif _is_tg_source(params.source):
        from .ingest import ingest_telegram

        meetings = ingest_telegram(
            params.source.replace("tg:", "").strip(),
            since=params.tg_since,
            limit=params.tg_limit,
            language=params.language or "ru",
            device=params.device,
            compute_type=params.compute_type,
            output_dir=params.output.parent if params.output else None,
            model=params.model,
        )
        if not meetings:
            return TranscribeResult(
                transcript_path=Path("nul"), transcript="", meta={"diarization": "none"}
            )
        first = meetings[0]
        transcript = "\n\n".join(
            f"[{u.date.strftime('%H:%M:%S')}] {u.speaker} | {u.transcript}"
            for u in first.utterances
        )
        folder = first.folder or Path(".")
        return TranscribeResult(
            transcript_path=folder, transcript=transcript, meta={"meetings": len(meetings)}
        )

    else:
        src = _resolve_source(params.source)

    if src.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        # ADR-012: картинка (фото-пост из TG или локальный файл) → vision-мост
        caption_path = src.with_suffix(".caption.txt")
        caption = (
            caption_path.read_text(encoding="utf-8").strip()
            if caption_path.exists()
            else ""
        )
        description = describe_image(src)
        transcript = (
            f"{caption}\n\n{description}" if caption else description
        ).strip()
        out = params.output or (src.parent / f"{src.stem}.transcript.txt")
        out.write_text(transcript, encoding="utf-8")
        log.info("Saved image description: %s", out)
        return TranscribeResult(transcript_path=out, transcript=transcript, meta={"vision": True})

    if not src.exists():
        fail(f"File not found: {src}")
    check_resource_limits(
        src,
        max_duration_sec=params.max_duration_sec,
        max_file_mb=params.max_file_mb,
    )
    audio = (
        src
        if src.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac"}
        else src.with_suffix(".wav")
    )
    if audio != src:
        extract_audio(src, audio)
    transcript, meta = transcribe_audio(
        audio, params.model, params.language, params.device, params.compute_type,
        diarize=params.diarize, num_speakers=params.num_speakers, recognize=params.recognize,
        speaker_label=params.speaker_label,
    )
    transcript = _clean_whisper_artifacts(transcript)
    out = params.output or (src.parent / f"{src.stem}.{NAMES_RU['transcript']}")
    out.write_text(transcript, encoding="utf-8")
    atomic_write_json(
        out.with_suffix(".transcript.json"), {"source_hash": sha256(src), **meta}
    )
    log.info("Saved transcript: %s", out)
    return TranscribeResult(transcript_path=out, transcript=transcript, meta=meta)


def translate(params: TranslateParams) -> TranslateResult:
    """Translate transcript lines to target language."""
    if not params.transcript.exists():
        fail(f"Transcript not found: {params.transcript}")
    lines = params.transcript.read_text(encoding="utf-8").splitlines()
    translated = translate_lines(lines, params.target_lang, allow_cloud=params.allow_cloud)
    out = params.output or params.transcript.with_suffix(".translated.txt")
    out.write_text("\n".join(translated), encoding="utf-8")
    log.info("Saved translation: %s", out)
    return TranslateResult(output_path=out, lines=translated)


def protocol(params: ProtocolParams) -> ProtocolResult:
    """Build and validate a meeting protocol from transcript."""
    if not params.transcript.exists():
        fail(f"Transcript not found: {params.transcript}")
    transcript = params.transcript.read_text(encoding="utf-8")
    if _needs_protocol_chunking(transcript):
        log.info("Transcript exceeds 6000 tokens; protocol will be chunked")
    proto = build_protocol(
        transcript,
        params.model,
        allow_cloud=params.allow_cloud,
        auto_attribute=not bool(params.participants),
    )
    if _protocol_verification_enabled():
        proto = _verify_protocol(
            proto, transcript, params.model, allow_cloud=params.allow_cloud
        )
    validation = validate_protocol(proto, transcript)
    replace_participant_labels(proto, params.participants)
    proto["schema_version"] = "0.1.0"
    proto["source_hash"] = sha256(params.transcript)
    proto["stt_model"] = params.model
    proto["llm_model"] = LLM_MODEL
    proto["created_at"] = _now_iso()
    proto["cloud_allowed"] = params.allow_cloud
    proto["parameters"] = {
        "model": params.model,
        "allow_cloud": params.allow_cloud,
    }
    proto["quality"] = validation
    out_path = params.output or params.transcript.with_suffix(".protocol.json")
    if validation["valid"]:
        atomic_write_json(out_path, proto)
        if params.docx:
            try:
                write_protocol_docx(proto, params.transcript.parent / NAMES_RU["protocol"])
            except PermissionError:
                from datetime import datetime

                fallback = params.transcript.parent / (
                    f"Протокол.{datetime.now().strftime('%H%M%S')}.docx"
                )
                write_protocol_docx(proto, fallback)
                log.warning("DOCX locked, saved to: %s", fallback)
        log.info("Saved protocol: %s", out_path)
    else:
        rejected = out_path.with_suffix(".protocol.rejected.json")
        atomic_write_json(rejected, proto)
        log.error("Invalid protocol saved to: %s", rejected)
    return ProtocolResult(
        protocol_path=out_path if validation["valid"] else None,
        protocol=proto,
        validation=validation,
        valid=validation["valid"],
    )


def process(params: ProcessParams) -> ProcessResult:
    """Run full pipeline: transcribe -> translate -> protocol."""
    tresult = transcribe(
        TranscribeParams(
            source=params.source,
            model=params.stt_model,
            language=params.language,
            device=params.device,
            compute_type=params.compute_type,
            diarize=params.diarize,
            num_speakers=params.num_speakers,
            recognize=params.recognize,
            max_duration_sec=params.max_duration_sec,
            max_file_mb=params.max_file_mb,
        )
    )
    src = _resolve_source(params.source)

    translated_path: Optional[Path] = None
    if not params.skip_translate:
        translated = translate_lines(
            tresult.transcript.splitlines(),
            params.target_lang,
            allow_cloud=params.allow_cloud,
        )
        translated_path = src.with_suffix(".translated.txt")
        translated_path.write_text("\n".join(translated), encoding="utf-8")
        log.info("Saved translation: %s", translated_path)

    proto = build_protocol(
        tresult.transcript,
        params.llm_model,
        allow_cloud=params.allow_cloud,
        auto_attribute=not bool(params.participants),
    )
    validation = validate_protocol(proto, tresult.transcript)
    replace_participant_labels(proto, params.participants)
    proto["quality"] = validation
    proto["schema_version"] = "0.1.0"
    proto["source_hash"] = sha256(tresult.transcript_path)
    proto["stt_model"] = params.stt_model
    proto["llm_model"] = params.llm_model
    proto["created_at"] = _now_iso()
    proto["cloud_allowed"] = params.allow_cloud
    proto["parameters"] = {
        "stt_model": params.stt_model,
        "llm_model": params.llm_model,
        "allow_cloud": params.allow_cloud,
        "target_lang": params.target_lang,
    }
    protocol_path = src.with_suffix(".protocol.json")
    if validation["valid"]:
        atomic_write_json(protocol_path, proto)
        if params.docx:
            write_protocol_docx(proto, src.parent / NAMES_RU["protocol"])
        log.info("Saved protocol: %s", protocol_path)
    else:
        rejected = protocol_path.with_suffix(".protocol.rejected.json")
        atomic_write_json(rejected, proto)
        log.error("Invalid protocol saved to: %s", rejected)

    return ProcessResult(
        transcript_path=tresult.transcript_path,
        transcript=tresult.transcript,
        translated_path=translated_path,
        protocol_path=protocol_path if validation["valid"] else None,
        protocol=proto,
        valid=validation["valid"],
    )


def agent_transcript(transcript_path: Path) -> dict:
    """Clean a transcript into JSON for agent consumption without an LLM call."""
    if not transcript_path.exists():
        fail(f"Transcript not found: {transcript_path}")
    return prepare_agent_transcript(
        transcript_path.read_text(encoding="utf-8"), transcript_path
    )
