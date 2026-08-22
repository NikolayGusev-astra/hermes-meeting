"""MCP tool surface: limit params must exist and reach the pipeline.

Deterministic-plugin goal: the agent calls meeting_transcribe /
meeting_process with explicit limits instead of the pipeline silently
rejecting 2h+ streams (default MEETING_MAX_DURATION_SEC=7200).

Signatures are parsed via AST (mcp/fastmcp is an optional dep, not needed
to verify the tool surface).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from meeting_intelligence import pipeline  # noqa: E402

SRC = Path(pipeline.__file__).resolve().parent / "mcp_server.py"


def _tool_sig(name: str) -> dict:
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            args = node.args
            defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
            return {
                a.arg: d for a, d in zip(args.args, defaults) if d is not None
            }
    raise AssertionError(f"tool {name} not found in mcp_server.py")


def test_meeting_transcribe_has_limit_params():
    sig = _tool_sig("meeting_transcribe")
    assert getattr(sig["max_duration_sec"], "value", None) == 0
    assert getattr(sig["max_file_mb"], "value", None) == 0


def test_meeting_process_has_limit_params():
    sig = _tool_sig("meeting_process")
    assert getattr(sig["max_duration_sec"], "value", None) == 0
    assert getattr(sig["max_file_mb"], "value", None) == 0


def test_transcribe_forwards_limits_to_check_resource_limits(tmp_path):
    """transcribe() must pass its limit params into check_resource_limits."""
    captured = {}

    def fake_limits(path, *, max_duration_sec=None, max_file_mb=None):
        captured["dur"] = max_duration_sec
        captured["mb"] = max_file_mb

    fake_wav = tmp_path / "in.wav"
    fake_wav.write_bytes(b"fake-wav")
    out = tmp_path / "out.txt"

    orig = (
        pipeline.check_resource_limits,
        pipeline._resolve_source,
        pipeline.extract_audio,
        pipeline.transcribe_audio,
    )
    try:
        pipeline.check_resource_limits = fake_limits
        pipeline._resolve_source = lambda s: fake_wav
        pipeline.extract_audio = lambda src, dst: dst
        pipeline.transcribe_audio = lambda *a, **k: ("t", {})
        res = pipeline.transcribe(
            pipeline.TranscribeParams(
                source="whatever",
                output=out,
                max_duration_sec=10800,
                max_file_mb=4096,
            )
        )
        assert captured == {"dur": 10800, "mb": 4096}
        assert res.transcript_path == out
    finally:
        (
            pipeline.check_resource_limits,
            pipeline._resolve_source,
            pipeline.extract_audio,
            pipeline.transcribe_audio,
        ) = orig


def test_process_forwards_limits():
    """process() must forward limit fields into TranscribeParams."""
    text = Path(pipeline.__file__).read_text(encoding="utf-8")
    assert "max_duration_sec=params.max_duration_sec" in text
    assert "max_file_mb=params.max_file_mb" in text
