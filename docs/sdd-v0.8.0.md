# SDD: meeting-intelligence v0.8.0

**Software Design Document** — Pipeline API + Dashboard + agent-plugins.org conformance  
**Date:** 2026-08-11  
**ADRs:** [007](adr/007-pipeline-api-extraction.md), [008](adr/008-web-dashboard.md),
[009](adr/009-agent-plugins-conformance.md)

---

## 1. Domain model (data shapes first)

```python
# src/meeting_intelligence/pipeline.py

@dataclass
class TranscribeParams:
    source: str            # local path or URL
    model: str = "small"
    language: str = "en"
    device: str = "cpu"    # "cpu" | "cuda"
    compute_type: str = "int8"
    output: Path | None = None

@dataclass
class TranscribeResult:
    transcript_path: Path
    transcript: str
    meta: dict

@dataclass
class TranslateParams:
    transcript: Path
    target_lang: str = "ru"
    allow_cloud: bool = False
    output: Path | None = None

@dataclass
class TranslateResult:
    output_path: Path
    lines: list[str]

@dataclass
class ProtocolParams:
    transcript: Path
    model: str = "qwen2.5-7b-instruct"
    allow_cloud: bool = False
    docx: bool = False
    participants: str | None = None
    output: Path | None = None

@dataclass
class ProtocolResult:
    protocol_path: Path | None     # None if validation failed
    protocol: dict
    validation: dict
    valid: bool

@dataclass
class ProcessParams:
    source: str
    stt_model: str = "small"
    llm_model: str = "qwen2.5-7b-instruct"
    language: str = "en"
    device: str = "cpu"
    compute_type: str = "int8"
    target_lang: str = "ru"
    skip_translate: bool = False
    docx: bool = False
    allow_cloud: bool = False
    participants: str | None = None

@dataclass
class ProcessResult:
    transcript_path: Path
    transcript: str
    translated_path: Path | None
    protocol_path: Path | None
    protocol: dict
    valid: bool
```

## 2. Module map

```
src/meeting_intelligence/
├── __init__.py            # __version__ (single source → 0.8.0)
├── cli.py                 # thin argparse adapter → pipeline functions
├── pipeline.py            # NEW: typed orchestration API (ADR-007)
├── transcribe.py          # unchanged
├── sources.py             # unchanged
├── language.py            # unchanged
├── gpu.py                 # unchanged
├── output/                # unchanged
├── protocol/              # unchanged
├── plugin/__init__.py     # register() → pipeline functions (no more stdout-capture)
├── mcp_server.py          # NEW: MCP stdio server (ADR-009)
└── web/                   # NEW: dashboard (ADR-008)
    ├── __init__.py
    ├── app.py
    ├── jobs.py
    └── templates/dashboard.html
```

## 3. Phase sequence (verifiable units)

| Phase | Deliverable | Verification |
|---|---|---|
| **1a** | `pipeline.py` typed API + `cli.py` refactor | `pytest -q` green; CLI output unchanged |
| **1b** | `plugin/__init__.py` delegates to pipeline | `test_plugin.py` green |
| **1c** | Hygiene: version sync, remove artifacts, LICENSE | version check passes |
| **2a** | `web/jobs.py` job store + pipeline runner | unit test: create→run→done |
| **2b** | `web/app.py` FastAPI routes + `dashboard.html` | `test_web.py`: upload + URL + poll + download |
| **2c** | `meeting serve` command + `[web]` extra | `meeting serve --help` works |
| **3a** | `plugin.json` + move `SKILL.md` → `skills/` | JSON validates against schema |
| **3b** | `mcp_server.py` + `mcp.json` | tool list matches 5 expected |
| **3c** | `SKILL.md` frontmatter cleanup | name matches parent dir |

## 4. Dashboard design (Phase 2)

**Single page** (`dashboard.html`):
- Tab/radio: **Upload file** | **Paste URL**
- Options: STT model (small/medium/large-v3-turbo), language, target-lang, LLM model
- Submit → POST `/api/jobs` → get job ID → poll `/api/jobs/{id}` every 2s
- On done: show transcript preview + protocol summary + download buttons

**Job lifecycle:**
```
pending → running → done
                  → error
```

**Background task:** `asyncio.create_task(run_pipeline(job_id, params))` — runs pipeline
in a thread executor (faster-whisper is blocking).

## 5. MCP server design (Phase 3)

`mcp_server.py` uses the `mcp` Python SDK (FastMCP pattern):
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("meeting-intelligence")

@mcp.tool()
def meeting_transcribe(source: str, model: str = "small", ...) -> str:
    result = pipeline.transcribe(TranscribeParams(source=source, model=model, ...))
    return json.dumps({"transcript_path": str(result.transcript_path), ...})
```

Five tools registered, schemas matching `plugin/__init__.py` exactly.

## 6. Versioning

Single source: `pyproject.toml` `version = "0.8.0"`. All manifests read from
`meeting_intelligence.__version__` which is set in `__init__.py` and kept in sync.
