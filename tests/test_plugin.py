"""Tests for Hermes plugin registration/behavior."""

from __future__ import annotations

import importlib.metadata
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
PY = sys.executable


class _Ctx:
    def __init__(self) -> None:
        self.tools = {}

    def register_tool(self, name, description, input_schema, output_schema, handler):
        self.tools[name] = dict(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            handler=handler,
        )


def test_plugin_entry_point_is_installed():
    eps = list(
        importlib.metadata.entry_points(
            group="hermes_agent.plugins", name="meeting-intelligence"
        )
    )
    assert eps, "missing plugin entry point meeting-intelligence"
    mod = eps[0].load()
    assert hasattr(mod, "register")


def test_plugin_registers_expected_tools():
    sys.path.insert(0, str(PROJECT / "src"))
    spec = importlib.util.spec_from_file_location(
        "meeting_intelligence.plugin",
        PROJECT / "src/meeting_intelligence/plugin/__init__.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ctx = _Ctx()
    mod.register(ctx)
    assert set(ctx.tools) == {
        "meeting_transcribe",
        "meeting_translate",
        "meeting_protocol",
        "meeting_process",
    }


def test_handler_invokes_exit_code_shape():
    sys.path.insert(0, str(PROJECT / "src"))
    spec = importlib.util.spec_from_file_location(
        "meeting_intelligence.plugin",
        PROJECT / "src/meeting_intelligence/plugin/__init__.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ctx = _Ctx()
    mod.register(ctx)
    handler = ctx.tools["meeting_protocol"]["handler"]
    res = handler(
        transcript="no real transcript here",
        model="qwen2.5-7b-instruct",
        allow_cloud=False,
        docx=False,
    )
    assert "exit_code" in res and "stderr" in res and "stdout" in res
