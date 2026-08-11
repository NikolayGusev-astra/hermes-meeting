#!/usr/bin/env python3
"""CLI adapter for meeting intelligence.

Thin argparse layer that delegates to pipeline.py (ADR-007).
All business logic lives in pipeline.py; this module only parses
arguments, formats output, and maps exit codes.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

# Re-export pipeline API for backward compatibility — tests and external
# consumers import validate_protocol, enforce_cloud_policy, etc. from cli.
from .pipeline import (  # noqa: F401
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    MAX_DURATION_SEC,
    MAX_FILE_MB,
    TRANSLATE_BATCH_SIZE,
    TRANSCRIBE_COMPUTE,
    TRANSCRIBE_DEVICE,
    TRANSCRIBE_LANG,
    TRANSCRIBE_MODEL,
    MeetingError,
    _chunked,
    _clean_whisper_artifacts,  # noqa: F401
    _handle_exception,
    _is_url,  # noqa: F401
    _now_iso,
    _participant_map,
    _probe_duration,
    _resolve_source,  # noqa: F401
    _translate_one,
    _normalize,
    atomic_write_json,
    check_resource_limits,
    enforce_cloud_policy,  # noqa: F401
    extract_audio,
    fail,  # noqa: F401
    is_loopback_url,
    replace_participant_labels,
    sha256,
    transcribe_audio,  # noqa: F401
    translate_lines,
    validate_protocol,  # noqa: F401
)
from .pipeline import (
    ProcessParams,
    ProtocolParams,
    TranscribeParams,
    TranslateParams,
    agent_transcript,
    process as run_process,
    protocol as run_protocol,
    transcribe as run_transcribe,
    translate as run_translate,
)
from .output import (  # noqa: F401
    prepare_agent_transcript,
    write_analytical_docx,
    write_protocol_docx,
    write_summary_docx,
    write_text_docx,
)
from .protocol import (  # noqa: F401
    _build_protocol_chunk,
    _protocol_verification_enabled,
    _verify_protocol,
)
from .protocol import chunk as _protocol_chunk  # noqa: F401
from .protocol.chunk import _needs_protocol_chunking  # noqa: F401


def build_protocol(transcript: str, model: str, allow_cloud: bool) -> dict:
    """Legacy CLI monkeypatch seam — delegates to protocol chunk builder.

    Kept here (not in pipeline.py) so tests can monkeypatch
    ``cli._build_protocol_chunk`` and have the change take effect.
    """
    return _protocol_chunk.build_protocol(
        transcript, model, allow_cloud, builder=_build_protocol_chunk
    )


log = logging.getLogger("meeting")


def _agent_mode_enabled() -> bool:
    return os.getenv("MEETING_AGENT_MODE", "false").lower() in {"1", "true", "yes", "on"}


# ── CLI command adapters ─────────────────────────────────────────────────


def cmd_agent_transcript(args: argparse.Namespace) -> int:
    """Emit a cleaned transcript JSON payload for agent consumption without an LLM call."""
    src = Path(args.transcript)
    if not src.exists():
        fail(f"Transcript not found: {src}")
    payload = agent_transcript(src)
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
    from .output import write_analytical_docx, write_protocol_docx, write_summary_docx

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
        write_analytical_docx(
            sections, output, str(payload.get("language", "en")) if payload else "en"
        )
    else:
        if payload:
            write_protocol_docx(payload, output)
        else:
            write_text_docx(output, "Meeting protocol", text.splitlines())
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    result = run_transcribe(
        TranscribeParams(
            source=args.source,
            model=args.model,
            language=args.language,
            device=args.device,
            compute_type=args.compute_type,
            output=Path(args.output) if getattr(args, "output", None) else None,
        )
    )
    if _agent_mode_enabled():
        print(json.dumps(prepare_agent_transcript(result.transcript, result.transcript_path)))
    return 0


def cmd_translate(args: argparse.Namespace) -> int:
    run_translate(
        TranslateParams(
            transcript=Path(args.transcript),
            target_lang=args.target_lang,
            allow_cloud=args.allow_cloud,
            output=Path(args.output) if getattr(args, "output", None) else None,
        )
    )
    return 0


def cmd_protocol(args: argparse.Namespace) -> int:
    result = run_protocol(
        ProtocolParams(
            transcript=Path(args.transcript),
            model=args.model,
            allow_cloud=args.allow_cloud,
            docx=getattr(args, "docx", False),
            participants=getattr(args, "participants", None),
            output=Path(args.output) if getattr(args, "output", None) else None,
        )
    )
    return 0 if result.valid else 3


def cmd_process(args: argparse.Namespace) -> int:
    result = run_process(
        ProcessParams(
            source=args.source,
            stt_model=args.stt_model,
            llm_model=args.llm_model,
            language=args.language,
            device=args.device,
            compute_type=args.compute_type,
            target_lang=args.target_lang,
            skip_translate=args.skip_translate,
            docx=args.docx,
            allow_cloud=args.allow_cloud,
            participants=getattr(args, "participants", None),
        )
    )
    return 0 if result.valid else 3


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
    generate_docx_p.add_argument(
        "--type", choices=("summary", "analytical", "protocol"), required=True
    )
    generate_docx_p.add_argument("--input", type=Path, required=True)
    generate_docx_p.add_argument("--output", type=Path, required=True)

    protocol_p = sub.add_parser("protocol")
    protocol_p.add_argument("transcript", type=Path)
    protocol_p.add_argument("--model", default=LLM_MODEL)
    protocol_p.add_argument("--allow-cloud", action="store_true", default=False)
    protocol_p.add_argument("--docx", action="store_true", default=False)
    protocol_p.add_argument(
        "--participants", default=None, help="SPEAKER_00=Имя,SPEAKER_01=Имя,..."
    )
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
    process_p.add_argument(
        "--participants", default=None, help="SPEAKER_00=Name,SPEAKER_01=Name,..."
    )
    process_p.add_argument("--output", type=Path, default=None)

    # Web dashboard
    serve_p = sub.add_parser("serve", help="Launch the web dashboard")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8000)

    args = p.parse_args()
    if not args.command:
        p.print_help()
        return 2

    if args.command == "serve":
        from .web.app import run_server

        return run_server(host=args.host, port=args.port)

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
