# ADR-007: Extract typed Pipeline API from cli.py

**Status:** Accepted  
**Date:** 2026-08-11  
**Supersedes:** plan-v0.7.1 P0 (partial)

## Context

`cli.py` mixes argparse-based CLI orchestration with reusable business logic. Every
`cmd_*` function accepts `argparse.Namespace` and prints results to stdout, returning an
integer exit code. This coupling blocks two consumers:

1. **Web dashboard** — needs callable Python functions with typed params, not subprocess-of-CLI.
2. **MCP server** (agent-plugins.org) — needs the same callable functions exposed as MCP tools.

Several helpers are already clean typed functions: `transcribe_audio()`,
`build_protocol()`, `validate_protocol()`, `translate_lines()`. The orchestration layer
(`cmd_transcribe`, `cmd_protocol`, `cmd_process`) is the missing piece — it's bound to
`argparse.Namespace` and returns `int` exit codes.

## Decision

Create `pipeline.py` with typed dataclass params + result objects for each operation:

```
pipeline.py
├── TranscribeParams  -> TranscribeResult
├── TranslateParams   -> TranslateResult
├── ProtocolParams    -> ProtocolResult
├── ProcessParams     -> ProcessResult
└── transcribe() / translate() / protocol() / process() / agent_transcript()
```

Functions accept **explicit typed parameters** (not `argparse.Namespace`), return
**result dataclasses** (not exit codes), and **write files** as a side effect (preserving
current behaviour for CLI users).

`cli.py` becomes a thin adapter: argparse → params dataclass → pipeline function →
format/print result.

## Consequences

- `cli.py` shrinks to ~200 lines of argument parsing.
- `plugin/__init__.py` (Hermes) and `mcp_server.py` (agent-plugins) both delegate to
  `pipeline.py` — single source of truth for orchestration.
- `register()` handlers call pipeline functions directly instead of wrapping `cmd_*`
  via stdout-capture (`_invoke`/`_handler` removed).
- Existing tests continue to pass (CLI output format unchanged).
