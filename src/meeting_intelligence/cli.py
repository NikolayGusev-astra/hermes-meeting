#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from importlib.util import find_spec
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from tenacity import retry, stop_after_attempt, wait_exponential

from .gpu import _transcribe_default_device
from .output import (
    prepare_agent_transcript,
    write_analytical_docx,
    write_protocol_docx,
    write_summary_docx,
    write_text_docx,
)
from .protocol import _build_protocol_chunk, _protocol_verification_enabled, _verify_protocol
from .protocol import chunk as _protocol_chunk
from .sources import MeetingError, _is_url, _resolve_source, fail
from .transcribe import _clean_whisper_artifacts, transcribe_audio


def build_protocol(transcript: str, model: str, allow_cloud: bool) -> dict:
    """Build a protocol while retaining the legacy CLI monkeypatch seam."""
    return _protocol_chunk.build_protocol(
        transcript, model, allow_cloud, builder=_build_protocol_chunk
    )

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("meeting")

# Suppress HuggingFace symlinks warning on Windows (harmless, just noisy)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

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











def _handle_exception(exc: Exception) -> None:
    msg = str(exc)
    log.error("Meeting pipeline error: %s", msg)
    raise MeetingError(msg) from exc


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()






def is_loopback_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1", ""}


def enforce_cloud_policy(allow_cloud: bool) -> None:
    if not allow_cloud and not is_loopback_url(LLM_BASE_URL):
        fail(
            f"Cloud LLM is disabled; external URL {LLM_BASE_URL!r}. "
            f"Pass --allow-cloud explicitly."
        )


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










def _agent_mode_enabled() -> bool:
    return os.getenv("MEETING_AGENT_MODE", "false").lower() in {"1", "true", "yes", "on"}




def cmd_agent_transcript(args: argparse.Namespace) -> int:
    """Emit a cleaned transcript JSON payload for agent consumption without an LLM call."""
    src = Path(args.transcript)
    if not src.exists():
        fail(f"Transcript not found: {src}")
    payload = prepare_agent_transcript(src.read_text(encoding="utf-8"), src)
    if getattr(args, "docx", False):
        output = (
            Path(args.output)
            if getattr(args, "output", None)
            else src.with_suffix(".agent-transcript.docx")
        )
        write_text_docx(output, src.stem, payload["transcript"].splitlines())
    print(json.dumps(payload))
    return 0


def _read_docx_input(path: Path) -> tuple[Optional[dict[str, Any]], str]:
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None, text
    if not isinstance(payload, dict):
        fail("DOCX JSON input must be an object")
    return payload, text


def cmd_generate_docx(args: argparse.Namespace) -> int:
    """Generate summary, analytical, or protocol DOCX from JSON or text input."""
    src = Path(args.input)
    if not src.exists():
        fail(f"Input not found: {src}")
    payload, text = _read_docx_input(src)
    output = Path(args.output)

    if args.type == "summary":
        if payload:
            write_summary_docx(
                str(payload.get("title", src.stem)),
                str(payload.get("speaker", "")),
                str(payload.get("duration", "")),
                payload.get("topics", []),
                output,
                payload.get("key_concepts", payload.get("concepts", [])),
                str(payload.get("language", "en")),
            )
        else:
            write_text_docx(output, src.stem, text.splitlines())
    elif args.type == "analytical":
        if payload:
            sections = payload.get("sections", payload)
            if not isinstance(sections, dict):
                fail("Analytical JSON input must contain an object of sections")
        else:
            sections = {"Context": text}
        write_analytical_docx(sections, output, str(payload.get("language", "en")) if payload else "en")
    else:
        if payload:
            write_protocol_docx(payload, output)
        else:
            write_text_docx(output, "Meeting protocol", text.splitlines())
    return 0


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _translate_one(client: Any, text: str, target_lang: str) -> str:
    prompt = f"Translate to {target_lang}. Keep names/codes/technical terms unchanged. Output ONLY translation, no extra text.\n\n{text}"
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
    chunk_buf = []
    prefix_buf = []
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
    participant_map = _participant_map(participants)
    for section in ["participants", "decisions", "assignments"]:
        for item in protocol.get(section, []):
            if not isinstance(item, dict):
                continue
            for field in ["name", "assignee", "approved_by"]:
                value = item.get(field)
                if isinstance(value, str) and value in participant_map:
                    item[field] = participant_map[value]
                elif isinstance(value, list):
                    item[field] = [participant_map.get(entry, entry) for entry in value]


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
            # Fuzzy match: quote words must appear in transcript
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
                    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2}[./:]\d{1,2}[./:]\d{2,4}|tmr|tomorrow|week|month|q[1-4])",
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


def atomic_write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path












def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_transcribe(args: argparse.Namespace) -> int:
    src = _resolve_source(args.source)
    if not src.exists():
        fail(f"File not found: {src}")
    check_resource_limits(src)
    audio = (
        src
        if src.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac"}
        else src.with_suffix(".wav")
    )
    if audio != src:
        extract_audio(src, audio)
    transcript, meta = transcribe_audio(
        audio, args.model, args.language, args.device, args.compute_type
    )
    transcript = _clean_whisper_artifacts(transcript)
    out = Path(args.output) if args.output else src.with_suffix(".transcript.txt")
    out.write_text(transcript, encoding="utf-8")
    atomic_write_json(
        out.with_suffix(".transcript.json"), {"source_hash": sha256(src), **meta}
    )
    log.info("Saved transcript: %s", out)
    if _agent_mode_enabled():
        print(json.dumps(prepare_agent_transcript(transcript, out)))
    return 0


def cmd_translate(args: argparse.Namespace) -> int:
    src = Path(args.transcript)
    if not src.exists():
        fail(f"Transcript not found: {src}")
    lines = src.read_text(encoding="utf-8").splitlines()
    translated = translate_lines(lines, args.target_lang, allow_cloud=args.allow_cloud)
    out = Path(args.output) if args.output else src.with_suffix(".translated.txt")
    out.write_text("\n".join(translated), encoding="utf-8")
    log.info("Saved translation: %s", out)
    return 0


def cmd_protocol(args: argparse.Namespace) -> int:
    """Build a protocol with the legacy pipeline (legacy — prefer agent-driven via SKILL.md)."""
    src = Path(args.transcript)
    if not src.exists():
        fail(f"Transcript not found: {src}")
    transcript = src.read_text(encoding="utf-8")
    if _needs_protocol_chunking(transcript):
        log.info("Transcript exceeds 6000 tokens; protocol will be chunked")
    protocol = build_protocol(transcript, args.model, allow_cloud=args.allow_cloud)
    if _protocol_verification_enabled():
        protocol = _verify_protocol(
            protocol, transcript, args.model, allow_cloud=args.allow_cloud
        )
    validation = validate_protocol(protocol, transcript)
    replace_participant_labels(protocol, getattr(args, "participants", None))
    protocol["schema_version"] = "0.1.0"
    protocol["source_hash"] = sha256(src)
    protocol["stt_model"] = args.model
    protocol["llm_model"] = LLM_MODEL
    protocol["created_at"] = _now_iso()
    protocol["cloud_allowed"] = args.allow_cloud
    protocol["parameters"] = {
        "model": args.model,
        "allow_cloud": args.allow_cloud,
        "target_lang": getattr(args, "target_lang", None),
    }
    protocol["quality"] = validation
    out_path = Path(args.output) if args.output else src.with_suffix(".protocol.json")
    if validation["valid"]:
        atomic_write_json(out_path, protocol)
        if getattr(args, "docx", False):
            try:
                write_protocol_docx(protocol, src.with_suffix(".protocol.docx"))
            except PermissionError:
                from datetime import datetime
                fallback = src.with_suffix(f".protocol.{datetime.now().strftime('%H%M%S')}.docx")
                write_protocol_docx(protocol, fallback)
                log.warning("DOCX locked, saved to: %s", fallback)
        log.info("Saved protocol: %s", out_path)
        return 0
    rejected = out_path.with_suffix(".protocol.rejected.json")
    atomic_write_json(rejected, protocol)
    log.error("Invalid protocol saved to: %s", rejected)
    return 3


def cmd_process(args: argparse.Namespace) -> int:
    """Run the legacy end-to-end pipeline (legacy — prefer agent-driven via SKILL.md)."""
    src = _resolve_source(args.source)
    if not src.exists():
        fail(f"File not found: {src}")
    check_resource_limits(src)
    audio = (
        src
        if src.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac"}
        else src.with_suffix(".wav")
    )
    if audio != src:
        extract_audio(src, audio)
    transcript, transcript_meta = transcribe_audio(
        audio, args.stt_model, args.language, args.device, args.compute_type
    )
    transcript = _clean_whisper_artifacts(transcript)
    transcript_path = src.with_suffix(".transcript.txt")
    transcript_path.write_text(transcript, encoding="utf-8")
    atomic_write_json(
        transcript_path.with_suffix(".transcript.json"),
        {"source_hash": sha256(src), **transcript_meta},
    )
    log.info("Saved transcript: %s", transcript_path)

    if not args.skip_translate:
        translated = translate_lines(
            transcript.splitlines(), args.target_lang, allow_cloud=args.allow_cloud
        )
        translated_path = src.with_suffix(".translated.txt")
        translated_path.write_text("\n".join(translated), encoding="utf-8")
        log.info("Saved translation: %s", translated_path)

    protocol = build_protocol(transcript, args.llm_model, allow_cloud=args.allow_cloud)
    validation = validate_protocol(protocol, transcript)
    replace_participant_labels(protocol, getattr(args, "participants", None))
    protocol["quality"] = validation
    protocol["schema_version"] = "0.1.0"
    protocol["source_hash"] = sha256(transcript_path)
    protocol["stt_model"] = args.stt_model
    protocol["llm_model"] = args.llm_model
    protocol["created_at"] = _now_iso()
    protocol["cloud_allowed"] = args.allow_cloud
    protocol["parameters"] = {
        "stt_model": args.stt_model,
        "llm_model": args.llm_model,
        "allow_cloud": args.allow_cloud,
        "target_lang": args.target_lang,
    }
    protocol_path = src.with_suffix(".protocol.json")
    if validation["valid"]:
        atomic_write_json(protocol_path, protocol)
        if args.docx:
            write_protocol_docx(protocol, src.with_suffix(".protocol.docx"))
        log.info("Saved protocol: %s", protocol_path)
    else:
        rejected = protocol_path.with_suffix(".protocol.rejected.json")
        atomic_write_json(rejected, protocol)
        log.error("Invalid protocol saved to: %s", rejected)
    if not validation["valid"]:
        return 3
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Meeting Intelligence CLI")
    sub = p.add_subparsers(dest="command")

    transcribe_p = sub.add_parser("transcribe")
    transcribe_p.add_argument("source")
    transcribe_p.add_argument("--model", default=TRANSCRIBE_MODEL)
    transcribe_p.add_argument("--language", default=TRANSCRIBE_LANG)
    transcribe_p.add_argument("--device", default=TRANSCRIBE_DEVICE)
    transcribe_p.add_argument("--compute-type", default=TRANSCRIBE_COMPUTE)
    transcribe_p.add_argument("--output", type=Path, default=None)

    translate_p = sub.add_parser("translate")
    translate_p.add_argument("transcript", type=Path)
    translate_p.add_argument("--target-lang", default="ru")
    translate_p.add_argument("--allow-cloud", action="store_true", default=False)
    translate_p.add_argument("--output", type=Path, default=None)

    agent_transcript_p = sub.add_parser(
        "agent-transcript",
        help="Emit a cleaned transcript JSON payload for agent consumption",
    )
    agent_transcript_p.add_argument("transcript", type=Path)
    agent_transcript_p.add_argument("--docx", action="store_true", default=False)
    agent_transcript_p.add_argument("--output", type=Path, default=None)

    generate_docx_p = sub.add_parser(
        "generate-docx", help="Generate DOCX from summary, analytical, or protocol content"
    )
    generate_docx_p.add_argument("--type", choices=("summary", "analytical", "protocol"), required=True)
    generate_docx_p.add_argument("--input", type=Path, required=True)
    generate_docx_p.add_argument("--output", type=Path, required=True)

    protocol_p = sub.add_parser("protocol")
    protocol_p.add_argument("transcript", type=Path)
    protocol_p.add_argument("--model", default=LLM_MODEL)
    protocol_p.add_argument("--allow-cloud", action="store_true", default=False)
    protocol_p.add_argument("--docx", action="store_true", default=False)
    protocol_p.add_argument("--participants", default=None, help="SPEAKER_00=Имя,SPEAKER_01=Имя,...")
    protocol_p.add_argument("--output", type=Path, default=None)

    process_p = sub.add_parser("process")
    process_p.add_argument("source")
    process_p.add_argument("--stt-model", default=TRANSCRIBE_MODEL)
    process_p.add_argument("--llm-model", default=LLM_MODEL)
    process_p.add_argument("--language", default=TRANSCRIBE_LANG)
    process_p.add_argument("--device", default=TRANSCRIBE_DEVICE)
    process_p.add_argument("--compute-type", default=TRANSCRIBE_COMPUTE)
    process_p.add_argument("--target-lang", default="ru")
    process_p.add_argument("--skip-translate", action="store_true", default=False)
    process_p.add_argument("--docx", action="store_true", default=False)
    process_p.add_argument("--allow-cloud", action="store_true", default=False)
    process_p.add_argument("--participants", default=None, help="SPEAKER_00=Name,SPEAKER_01=Name,...")
    process_p.add_argument("--output", type=Path, default=None)

    args = p.parse_args()
    if not args.command:
        p.print_help()
        return 2

    try:
        if args.command == "transcribe":
            return cmd_transcribe(args)
        if args.command == "translate":
            return cmd_translate(args)
        if args.command == "agent-transcript":
            return cmd_agent_transcript(args)
        if args.command == "generate-docx":
            return cmd_generate_docx(args)
        if args.command == "protocol":
            return cmd_protocol(args)
        if args.command == "process":
            return cmd_process(args)
    except MeetingError as exc:
        fail(str(exc))
    fail("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
