"""Tests for Hermes plugin registration/behavior."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import sys
import tomllib
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
PY = sys.executable
sys.path.insert(0, str(PROJECT / "src"))


class _Ctx:
    def __init__(self) -> None:
        self.tools = {}

    def register_tool(self, name, toolset, schema, handler):
        self.tools[name] = dict(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
        )


def test_plugin_entry_point_is_declared_and_loadable_from_source():
    config = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    target = config["project"]["entry-points"]["hermes_agent.plugins"][
        "meeting-intelligence"
    ]
    module_name, _, attribute = target.partition(":")
    mod = importlib.import_module(module_name)
    if attribute:
        assert getattr(mod, attribute)
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
        "meeting_agent_transcript",
        "meeting_protocol",
        "meeting_process",
    }
    for name, tool in ctx.tools.items():
        assert tool["toolset"] == "meeting_intelligence"
        assert tool["schema"]["name"] == name
        assert "description" in tool["schema"]
        assert tool["schema"]["parameters"]["type"] == "object"


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
    res = json.loads(handler({"transcript": "no real transcript here"}))
    assert "exit_code" in res and "stderr" in res and "stdout" in res


def test_agent_transcript_handler_returns_cleaned_payload(tmp_path):
    sys.path.insert(0, str(PROJECT / "src"))
    spec = importlib.util.spec_from_file_location(
        "meeting_intelligence.plugin",
        PROJECT / "src/meeting_intelligence/plugin/__init__.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    transcript = tmp_path / "meeting.txt"
    transcript.write_text("[seg_0001] hello", encoding="utf-8")
    ctx = _Ctx()
    mod.register(ctx)

    result = json.loads(ctx.tools["meeting_agent_transcript"]["handler"]({"transcript": str(transcript)}))

    assert result["exit_code"] == 0
    assert json.loads(result["stdout"])["transcript"] == "hello"
