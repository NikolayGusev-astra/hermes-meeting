# ADR-008: Web dashboard architecture

**Status:** Accepted  
**Date:** 2026-08-11

## Context

The pipeline is slow: a 1-hour meeting takes minutes for Whisper transcription plus
LLM-based protocol extraction. A synchronous HTTP handler would block the browser and
time out. Users need a simple UI to upload a media file **or** paste a download URL,
trigger processing, and download transcript/protocol outputs.

## Decision

**FastAPI + asyncio background tasks + single-page HTML**, packaged as an optional
`[web]` extra inside `meeting-intelligence`.

```
src/meeting_intelligence/web/
├── __init__.py
├── app.py          # FastAPI app: routes, background tasks, job store
├── jobs.py         # In-memory job store + status (pending/running/done/error)
└── templates/
    └── dashboard.html   # Single page: upload/URL form + status + results
```

- **POST /api/jobs** — accept multipart file upload **or** JSON with a URL; create job,
  spawn `asyncio.create_task` running the pipeline.
- **GET /api/jobs/{id}** — poll status + progress + result paths.
- **GET /api/jobs/{id}/files/{name}** — download transcript/protocol/docx.
- **GET /** — serve the dashboard HTML page.

New CLI command: `meeting serve [--host 0.0.0.0] [--port 8000]`.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Synchronous handler | Blocks browser for minutes; timeouts on long audio |
| Separate repository | Duplicates packaging; extra deployable |
| Dashboard-over-MCP (stdio) | MCP stdio awkward for a web backend; transport mismatch |
| Celery/Redis queue | Overkill for local single-user; adds infra deps |

## Consequences

- New dependencies behind `[web]` extra: `fastapi`, `uvicorn`, `python-multipart`.
- In-memory job store (no DB) — jobs lost on restart. Acceptable for local tool.
- No auth — local-only by default; bind to `127.0.0.1`.
- Shares the pipeline API with CLI and MCP server (ADR-007).
