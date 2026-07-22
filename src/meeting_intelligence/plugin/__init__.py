"""Hermes plugin registration for meeting intelligence tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meeting_intelligence.cli import (
    cmd_process,
    cmd_protocol,
    cmd_transcribe,
    cmd_translate,
)


def _invoke(fn: Callable[[argparse.Namespace], int], args: argparse.Namespace) -> dict:
    try:
        rc = fn(args)
    except SystemExit as exc:
        rc = int(exc.code) if exc.code is not None else 2
    except Exception as exc:
        return {"exit_code": 2, "stdout": "", "stderr": str(exc)}
    return {"exit_code": int(rc), "stdout": "", "stderr": ""}


def _handler(fn: Callable[[argparse.Namespace], int], defaults: dict) -> Callable:
    def handler(params: dict, **kwargs: Any) -> str:
        del kwargs
        args = argparse.Namespace(**(defaults | params))
        return json.dumps(_invoke(fn, args))

    return handler


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
        handler=_handler(
            cmd_transcribe,
            {"model": "small", "language": "en", "device": "cpu", "compute_type": "int8", "output": None},
        ),
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
        handler=_handler(cmd_translate, {"target_lang": "ru", "allow_cloud": False, "output": None}),
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
        handler=_handler(
            cmd_protocol,
            {"model": "qwen2.5-7b-instruct", "allow_cloud": False, "docx": False, "output": None},
        ),
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
        handler=_handler(
            cmd_process,
            {
                "stt_model": "small",
                "llm_model": "qwen2.5-7b-instruct",
                "language": "en",
                "device": "cpu",
                "compute_type": "int8",
                "target_lang": "ru",
                "skip_translate": False,
                "docx": False,
                "allow_cloud": False,
            },
        ),
    )
