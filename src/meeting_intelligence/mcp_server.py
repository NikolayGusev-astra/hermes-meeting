"""MCP stdio server exposing meeting intelligence tools.

Implements the agent-plugins.org v1.0.0 MCP component (ADR-009).
Uses FastMCP to expose the five pipeline tools over stdio.

Run directly:
    python -m meeting_intelligence.mcp_server

Or via agent-plugins.org mcp.json (see repo root).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure src is on path when run as a module without installation
_src = Path(__file__).resolve().parents[1]
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from mcp.server.fastmcp import FastMCP

from . import pipeline
from .pipeline import (
    ProcessParams,
    ProtocolParams,
    TranscribeParams,
    TranslateParams,
)
from .sources import MeetingError

mcp = FastMCP("meeting-intelligence")


def _error_payload(code: int, msg: str) -> str:
    return json.dumps({"error": True, "exit_code": code, "message": msg}, ensure_ascii=False)


@mcp.tool()
def meeting_transcribe(
    source: str,
    model: str = "small",
    language: str = "en",
    device: str = "cpu",
    compute_type: str = "int8",
    diarize: bool = False,
    num_speakers: int = 0,
    output: str = "",
) -> str:
    """Transcribe audio/video to a timestamped transcript file.

    Args:
        source: Local file path or media URL.
        model: Whisper model size (tiny, base, small, medium, large-v3-turbo).
        language: Source language code (en, ru, de, ...).
        device: cpu or cuda.
        compute_type: Whisper compute type (int8, float16, ...).
        diarize: Enable speaker diarization (pyannote, offline; groups real speakers).
        num_speakers: Optional exact number of speakers (helps clustering); 0 = auto.
        output: Optional output file path.

    Returns:
        JSON with transcript_path and meta, or error envelope.
    """
    try:
        result = pipeline.transcribe(
            TranscribeParams(
                source=source,
                model=model,
                language=language,
                device=device,
                compute_type=compute_type,
                output=Path(output) if output else None,
                diarize=diarize,
                num_speakers=(num_speakers or None),
            )
        )
        return json.dumps(
            {"transcript_path": str(result.transcript_path), "meta": result.meta},
            ensure_ascii=False,
        )
    except SystemExit as exc:
        return _error_payload(int(exc.code) if exc.code is not None else 2, "")
    except (MeetingError, Exception) as exc:
        return _error_payload(2, str(exc))


@mcp.tool()
def meeting_translate(
    transcript: str,
    target_lang: str = "ru",
    allow_cloud: bool = False,
    output: str = "",
) -> str:
    """Translate a timestamped transcript to the target language.

    Args:
        transcript: Path to the transcript file.
        target_lang: Target language code.
        allow_cloud: Allow external (cloud) LLM endpoints.
        output: Optional output file path.

    Returns:
        JSON with output_path, or error envelope.
    """
    try:
        result = pipeline.translate(
            TranslateParams(
                transcript=Path(transcript),
                target_lang=target_lang,
                allow_cloud=allow_cloud,
                output=Path(output) if output else None,
            )
        )
        return json.dumps({"output_path": str(result.output_path)}, ensure_ascii=False)
    except SystemExit as exc:
        return _error_payload(int(exc.code) if exc.code is not None else 2, "")
    except (MeetingError, Exception) as exc:
        return _error_payload(2, str(exc))


@mcp.tool()
def meeting_agent_transcript(transcript: str) -> str:
    """Clean a transcript into JSON for agent analysis without calling an LLM.

    Args:
        transcript: Path to the transcript file.

    Returns:
        JSON payload with cleaned transcript text, or error envelope.
    """
    try:
        payload = pipeline.agent_transcript(Path(transcript))
        return json.dumps(payload, ensure_ascii=False)
    except SystemExit as exc:
        return _error_payload(int(exc.code) if exc.code is not None else 2, "")
    except (MeetingError, Exception) as exc:
        return _error_payload(2, str(exc))


@mcp.tool()
def meeting_protocol(
    transcript: str,
    model: str = "qwen2.5-7b-instruct",
    allow_cloud: bool = False,
    docx: bool = False,
    output: str = "",
) -> str:
    """Extract a validated meeting protocol (decisions, assignments) from a transcript.

    Args:
        transcript: Path to the transcript file.
        model: LLM model name for protocol extraction.
        allow_cloud: Allow external (cloud) LLM endpoints.
        docx: Also write a DOCX version of the protocol.
        output: Optional output file path.

    Returns:
        JSON with protocol_path, valid, and validation details.
    """
    try:
        result = pipeline.protocol(
            ProtocolParams(
                transcript=Path(transcript),
                model=model,
                allow_cloud=allow_cloud,
                docx=docx,
                output=Path(output) if output else None,
            )
        )
        return json.dumps(
            {
                "protocol_path": str(result.protocol_path) if result.protocol_path else None,
                "valid": result.valid,
                "validation": result.validation,
            },
            ensure_ascii=False,
        )
    except SystemExit as exc:
        return _error_payload(int(exc.code) if exc.code is not None else 2, "")
    except (MeetingError, Exception) as exc:
        return _error_payload(2, str(exc))


@mcp.tool()
def meeting_process(
    source: str,
    stt_model: str = "small",
    llm_model: str = "qwen2.5-7b-instruct",
    language: str = "en",
    device: str = "cpu",
    compute_type: str = "int8",
    target_lang: str = "ru",
    skip_translate: bool = False,
    docx: bool = False,
    allow_cloud: bool = False,
    diarize: bool = False,
    num_speakers: int = 0,
) -> str:
    """Full pipeline: transcribe audio/video → translate → extract protocol.

    Args:
        source: Local file path or media URL.
        stt_model: Whisper model for speech-to-text.
        llm_model: LLM model for protocol extraction.
        language: Source language code.
        device: cpu or cuda.
        compute_type: Whisper compute type.
        target_lang: Target language for translation.
        skip_translate: Skip the translation step.
        docx: Also write DOCX outputs.
        allow_cloud: Allow external (cloud) LLM endpoints.

    Returns:
        JSON with transcript_path, protocol_path, and validity flag.
    """
    try:
        result = pipeline.process(
            ProcessParams(
                source=source,
                stt_model=stt_model,
                llm_model=llm_model,
                language=language,
                device=device,
                compute_type=compute_type,
                target_lang=target_lang,
                skip_translate=skip_translate,
                docx=docx,
                allow_cloud=allow_cloud,
                diarize=diarize,
                num_speakers=(num_speakers or None),
            )
        )
        return json.dumps(
            {
                "transcript_path": str(result.transcript_path),
                "translated_path": str(result.translated_path) if result.translated_path else None,
                "protocol_path": str(result.protocol_path) if result.protocol_path else None,
                "valid": result.valid,
            },
            ensure_ascii=False,
        )
    except SystemExit as exc:
        return _error_payload(int(exc.code) if exc.code is not None else 2, "")
    except (MeetingError, Exception) as exc:
        return _error_payload(2, str(exc))


def main() -> None:
    """Entry point for `python -m meeting_intelligence.mcp_server`."""
    mcp.run()


if __name__ == "__main__":
    main()
