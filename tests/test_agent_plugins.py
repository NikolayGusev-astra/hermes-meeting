"""Tests for agent-plugins.org v1.0.0 conformance (ADR-009)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))


# ── plugin.json manifest ─────────────────────────────────────────────────


def test_plugin_json_exists_and_is_valid_manifest():
    manifest_path = PROJECT / "plugin.json"
    assert manifest_path.exists(), "plugin.json must exist at repo root"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert manifest["name"] == "meeting-intelligence"
    assert manifest["version"]
    assert manifest["description"]
    assert manifest["license"] == "MIT"


def test_plugin_json_name_format_valid():
    """Name must be 1-64 chars, lowercase a-z 0-9 - ., alphanumeric start/end."""
    manifest = json.loads((PROJECT / "plugin.json").read_text(encoding="utf-8"))
    name = manifest["name"]
    assert 1 <= len(name) <= 64
    assert name[0].isalnum()
    assert name[-1].isalnum()
    assert all(c.islower() or c.isdigit() or c in "-." for c in name)
    assert "--" not in name
    assert ".." not in name


def test_plugin_json_extensions_preserve_hermes_native():
    manifest = json.loads((PROJECT / "plugin.json").read_text(encoding="utf-8"))
    assert "extensions" in manifest
    assert "ru.hermes" in manifest["extensions"]
    assert "entrypoint" in manifest["extensions"]["ru.hermes"]


# ── mcp.json ─────────────────────────────────────────────────────────────


def test_mcp_json_exists_and_declares_stdio_server():
    mcp_path = PROJECT / "mcp.json"
    assert mcp_path.exists(), "mcp.json must exist at repo root"

    config = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert config["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    assert "mcpServers" in config
    assert "meeting-intelligence" in config["mcpServers"]

    server = config["mcpServers"]["meeting-intelligence"]
    assert server["type"] == "stdio"
    assert server["command"]
    assert isinstance(server["args"], list)


# ── Skills directory structure ───────────────────────────────────────────


def test_skill_md_moved_to_skills_directory():
    """SKILL.md must be under skills/<name>/ per agent-plugins.org §7.1."""
    old_location = PROJECT / "SKILL.md"
    assert not old_location.exists(), "SKILL.md must not be at repo root"

    skill_path = PROJECT / "skills" / "meeting-intelligence" / "SKILL.md"
    assert skill_path.exists(), "SKILL.md must be at skills/meeting-intelligence/SKILL.md"


def test_skill_frontmatter_conforms_to_agent_skills_spec():
    """Frontmatter must have name + description; extras in metadata."""
    import yaml

    skill_path = PROJECT / "skills" / "meeting-intelligence" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")
    assert content.startswith("---")

    parts = content.split("---", 2)
    fm = yaml.safe_load(parts[1])

    # Required fields
    assert fm["name"] == "meeting-intelligence"
    assert "description" in fm and fm["description"]

    # name matches parent directory
    assert fm["name"] == "meeting-intelligence"

    # Non-standard fields must be under metadata
    standard_keys = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    extra_keys = set(fm.keys()) - standard_keys
    assert not extra_keys, f"Non-standard frontmatter keys outside metadata: {extra_keys}"


# ── MCP server tool registration ─────────────────────────────────────────


def test_mcp_server_registers_five_tools():
    from meeting_intelligence.mcp_server import mcp

    tools = mcp._tool_manager._tools
    expected = {
        "meeting_transcribe",
        "meeting_translate",
        "meeting_agent_transcript",
        "meeting_protocol",
        "meeting_process",
    }
    assert set(tools.keys()) == expected


def test_mcp_agent_transcript_tool_works(tmp_path):
    """The agent_transcript MCP tool doesn't need LLM — test it end-to-end."""
    from meeting_intelligence.mcp_server import meeting_agent_transcript

    transcript = tmp_path / "meeting.txt"
    transcript.write_text("[seg_0001] hello world", encoding="utf-8")

    result = json.loads(meeting_agent_transcript(str(transcript)))
    assert result["transcript"] == "hello world"
