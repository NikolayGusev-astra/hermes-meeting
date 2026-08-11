# ADR-009: agent-plugins.org v1.0.0 conformance

**Status:** Accepted  
**Date:** 2026-08-11

## Context

The audit (2026-08-11) found the solution does **not** conform to the agent-plugins.org
v1.0.0 portable plugin concept. Current `plugin.yaml` is a Hermes-specific manifest
(YAML, with `entrypoint` + `tools`), not the standard `plugin.json`. The `SKILL.md` sits
at the repo root instead of `skills/<name>/`. There is no `mcp.json` and the five tools
are exposed via imperative `register(ctx)` Python callables — a concept that does not
exist in the portable format.

agent-plugins.org v1 exposes capability through exactly two component types:
**Agent Skills** (`skills/<name>/SKILL.md`) and **MCP servers** (`mcp.json`). Both must
be discoverable at fixed locations alongside a `plugin.json` manifest.

## Decision

Adopt **dual packaging** — add the portable format while keeping Hermes-native compat:

```
hermes-meeting/
├── plugin.json                          # NEW: portable manifest (ADR-009)
├── plugin.yaml                          # KEEP: Hermes-native (via extensions)
├── mcp.json                             # NEW: MCP server config
├── skills/
│   └── meeting-intelligence/
│       └── SKILL.md                     # MOVED from repo root
├── src/meeting_intelligence/
│   ├── pipeline.py                      # ADR-007
│   ├── mcp_server.py                    # NEW: stdio MCP server wrapping pipeline API
│   └── web/                             # ADR-008
└── ...
```

**plugin.json** (JSON, schema-conformant):
```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "meeting-intelligence",
  "version": "0.8.0",
  "description": "Local-first meeting intelligence: transcription, translation, protocol",
  "license": "MIT",
  "repository": "https://github.com/NikolayGusev-astra/hermes-meeting",
  "extensions": { "ru.hermes": { "entrypoint": "meeting_intelligence.plugin:register" } }
}
```

**mcp.json**:
```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "meeting-intelligence": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "meeting_intelligence.mcp_server"],
      "env": {}
    }
  }
}
```

The MCP server (`mcp_server.py`) exposes the five tools using the MCP Python SDK,
delegating to `pipeline.py`. Schemas are reused 1:1 from `plugin/__init__.py`.

`SKILL.md` frontmatter is cleaned: non-standard fields (`when_to_use`,
`counter_triggers`, `required_tools`, `optional_mcp`) move into `metadata`.

## Consequences

- The plugin is loadable by any agent-plugins.org-conformant client (Claude Code, etc.)
  **and** by Hermes (via `plugin.yaml` + Python entrypoint).
- `plugin.json` `extensions.ru.hermes` preserves the Hermes-native path without polluting
  the portable schema.
- MCP server needs the package installed + heavy deps (faster-whisper, ffmpeg) in the
  environment — documented in skill `compatibility`.
- Version becomes single-sourced from `pyproject.toml` → synced to all manifests.
