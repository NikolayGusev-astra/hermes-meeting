"""Hermes plugin registration for meeting intelligence tools.

Delegates to pipeline.py typed API (ADR-007). Handlers return the legacy
{exit_code, stdout, stderr} JSON envelope for Hermes compat, but populate
it from structured pipeline results instead of stdout-capture.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from .. import pipeline
from ..pipeline import (
    ProcessParams,
    ProtocolParams,
    TranscribeParams,
    TranslateParams,
)
from ..sources import MeetingError


def _schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def _ok(payload: dict) -> str:
    return json.dumps(
        {"exit_code": 0, "stdout": json.dumps(payload, ensure_ascii=False), "stderr": ""},
        ensure_ascii=False,
    )


def _err(code: int, msg: str) -> str:
    return json.dumps({"exit_code": code, "stdout": "", "stderr": msg}, ensure_ascii=False)


def _safe(fn: Callable[[], dict]) -> str:
    try:
        return _ok(fn())
    except SystemExit as exc:
        code = int(exc.code) if exc.code is not None else 2
        return _err(code, "")
    except MeetingError as exc:
        return _err(2, str(exc))
    except Exception as exc:
        return _err(2, str(exc))


def _protocol_payload(params: dict) -> dict:
    r = pipeline.protocol(ProtocolParams(
        transcript=Path(params["transcript"]),
        model=params.get("model", "qwen2.5-7b-instruct"),
        allow_cloud=params.get("allow_cloud", False),
        docx=params.get("docx", False),
        output=Path(params["output"]) if params.get("output") else None,
    ))
    return {
        "protocol_path": str(r.protocol_path) if r.protocol_path else None,
        "valid": r.valid,
        "validation": r.validation,
    }


def _process_payload(params: dict) -> dict:
    r = pipeline.process(ProcessParams(
        source=params["source"],
        stt_model=params.get("stt_model", "small"),
        llm_model=params.get("llm_model", "qwen2.5-7b-instruct"),
        language=params.get("language", "en"),
        device=params.get("device", "cpu"),
        compute_type=params.get("compute_type", "int8"),
        target_lang=params.get("target_lang", "ru"),
        skip_translate=params.get("skip_translate", False),
        docx=params.get("docx", False),
        allow_cloud=params.get("allow_cloud", False),
    ))
    return {
        "transcript_path": str(r.transcript_path),
        "translated_path": str(r.translated_path) if r.translated_path else None,
        "protocol_path": str(r.protocol_path) if r.protocol_path else None,
        "valid": r.valid,
    }


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="meeting_transcribe",
        toolset="meeting_intelligence",
        schema=_schema(
            "meeting_transcribe",
            "Transcribe audio/video to timestamped transcript",
            {
                "source": {"type": "string"},
                "model": {"type": "string", "default": "small"},
                "language": {"type": "string", "default": "en"},
                "device": {"type": "string", "default": "cpu", "enum": ["cpu", "cuda"]},
                "compute_type": {"type": "string", "default": "int8"},
                "output": {"type": "string"},
            },
            ["source"],
        ),
        handler=lambda params, **kw: _safe(lambda: {
            "transcript_path": str(
                pipeline.transcribe(TranscribeParams(
                    source=params["source"],
                    model=params.get("model", "small"),
                    language=params.get("language", "en"),
                    device=params.get("device", "cpu"),
                    compute_type=params.get("compute_type", "int8"),
                    output=Path(params["output"]) if params.get("output") else None,
                )).transcript_path
            )
        }),
    )

    ctx.register_tool(
        name="meeting_translate",
        toolset="meeting_intelligence",
        schema=_schema(
            "meeting_translate",
            "Translate timestamped transcript",
            {
                "transcript": {"type": "string"},
                "target_lang": {"type": "string", "default": "ru"},
                "allow_cloud": {"type": "boolean", "default": False},
                "output": {"type": "string"},
            },
            ["transcript"],
        ),
        handler=lambda params, **kw: _safe(lambda: {
            "output_path": str(
                pipeline.translate(TranslateParams(
                    transcript=Path(params["transcript"]),
                    target_lang=params.get("target_lang", "ru"),
                    allow_cloud=params.get("allow_cloud", False),
                    output=Path(params["output"]) if params.get("output") else None,
                )).output_path
            )
        }),
    )

    ctx.register_tool(
        name="meeting_agent_transcript",
        toolset="meeting_intelligence",
        schema=_schema(
            "meeting_agent_transcript",
            "Clean a transcript into JSON for agent analysis without calling an LLM",
            {"transcript": {"type": "string"}},
            ["transcript"],
        ),
        handler=lambda params, **kw: _safe(lambda: pipeline.agent_transcript(
            Path(params["transcript"])
        )),
    )

    ctx.register_tool(
        name="meeting_protocol",
        toolset="meeting_intelligence",
        schema=_schema(
            "meeting_protocol",
            "Extract validated meeting protocol from transcript",
            {
                "transcript": {"type": "string"},
                "model": {"type": "string", "default": "qwen2.5-7b-instruct"},
                "allow_cloud": {"type": "boolean", "default": False},
                "docx": {"type": "boolean", "default": False},
                "output": {"type": "string"},
            },
            ["transcript"],
        ),
        handler=lambda params, **kw: _safe(lambda: _protocol_payload(params)),
    )

    ctx.register_tool(
        name="meeting_process",
        toolset="meeting_intelligence",
        schema=_schema(
            "meeting_process",
            "Full pipeline: audio -> transcript -> translation -> protocol",
            {
                "source": {"type": "string"},
                "stt_model": {"type": "string", "default": "small"},
                "llm_model": {"type": "string", "default": "qwen2.5-7b-instruct"},
                "language": {"type": "string", "default": "en"},
                "device": {"type": "string", "default": "cpu", "enum": ["cpu", "cuda"]},
                "compute_type": {"type": "string", "default": "int8"},
                "target_lang": {"type": "string", "default": "ru"},
                "skip_translate": {"type": "boolean", "default": False},
                "docx": {"type": "boolean", "default": False},
                "allow_cloud": {"type": "boolean", "default": False},
            },
            ["source"],
        ),
        handler=lambda params, **kw: _safe(lambda: _process_payload(params)),
    )
