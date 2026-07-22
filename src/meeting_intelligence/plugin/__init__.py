"""Hermes plugin registration for meeting intelligence tools."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meeting_intelligence.cli import (
    cmd_process,
    cmd_protocol,
    cmd_transcribe,
    cmd_translate,
)


def _invoke(fn, **kwargs):
    try:
        rc = fn(**kwargs)
    except SystemExit as exc:
        rc = int(exc.code) if exc.code is not None else 2
    except Exception as exc:
        return {"exit_code": 2, "stdout": "", "stderr": str(exc)}
    return {"exit_code": int(rc), "stdout": "", "stderr": ""}


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="meeting_transcribe",
        description="Transcribe audio/video to timestamped transcript",
        input_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "model": {"type": "string", "default": "small"},
                "language": {"type": "string", "default": "en"},
                "device": {"type": "string", "default": "cpu", "enum": ["cpu", "cuda"]},
                "compute_type": {"type": "string", "default": "int8"},
            },
            "required": ["source"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "exit_code": {"type": "integer"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
            },
        },
        handler=lambda source, model="small", language="en", device="cpu", compute_type="int8": (
            _invoke(
                cmd_transcribe,
                source=Path(source),
                model=model,
                language=language,
                device=device,
                compute_type=compute_type,
            )
        ),
    )

    ctx.register_tool(
        name="meeting_translate",
        description="Translate timestamped transcript",
        input_schema={
            "type": "object",
            "properties": {
                "transcript": {"type": "string"},
                "target_lang": {"type": "string", "default": "ru"},
                "allow_cloud": {"type": "boolean", "default": False},
            },
            "required": ["transcript"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "exit_code": {"type": "integer"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
            },
        },
        handler=lambda transcript, target_lang="ru", allow_cloud=False: _invoke(
            cmd_translate,
            transcript=Path(transcript),
            target_lang=target_lang,
            allow_cloud=allow_cloud,
        ),
    )

    ctx.register_tool(
        name="meeting_protocol",
        description="Extract validated meeting protocol from transcript",
        input_schema={
            "type": "object",
            "properties": {
                "transcript": {"type": "string"},
                "model": {"type": "string", "default": "qwen2.5-7b-instruct"},
                "allow_cloud": {"type": "boolean", "default": False},
                "docx": {"type": "boolean", "default": False},
            },
            "required": ["transcript"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "exit_code": {"type": "integer"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
            },
        },
        handler=lambda transcript, model="qwen2.5-7b-instruct", allow_cloud=False, docx=False: (
            _invoke(
                cmd_protocol,
                transcript=Path(transcript),
                model=model,
                allow_cloud=allow_cloud,
                docx=docx,
            )
        ),
    )

    ctx.register_tool(
        name="meeting_process",
        description="Full pipeline: audio -> transcript -> translation -> protocol",
        input_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "model": {"type": "string", "default": "small"},
                "language": {"type": "string", "default": "en"},
                "device": {"type": "string", "default": "cpu", "enum": ["cpu", "cuda"]},
                "compute_type": {"type": "string", "default": "int8"},
                "target_lang": {"type": "string", "default": "ru"},
                "skip_translate": {"type": "boolean", "default": False},
                "docx": {"type": "boolean", "default": False},
                "allow_cloud": {"type": "boolean", "default": False},
            },
            "required": ["source"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "exit_code": {"type": "integer"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
            },
        },
        handler=lambda source, model="small", language="en", device="cpu", compute_type="int8", target_lang="ru", skip_translate=False, docx=False, allow_cloud=False: (
            _invoke(
                cmd_process,
                source=Path(source),
                model=model,
                language=language,
                device=device,
                compute_type=compute_type,
                target_lang=target_lang,
                skip_translate=skip_translate,
                docx=docx,
                allow_cloud=allow_cloud,
            )
        ),
    )
