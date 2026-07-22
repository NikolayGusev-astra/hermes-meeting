# Meeting Intelligence

Local-first meeting processing: audio/video → timestamped transcript → translation → validated protocol.

Optional Hermes plugin integration via `meeting-intelligence`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install .
```

## CLI

```bash
meeting transcribe meeting.mp4 --model small --language en --device cpu
meeting translate meeting.transcript.txt --target-lang ru --allow-cloud
meeting protocol meeting.transcript.txt --model qwen2.5-7b-instruct
meeting process meeting.mp4 --language en --target-lang ru --docx
```

## Hermes plugin

Register in Hermes config:

```yaml
plugins:
  enabled:
    - meeting-intelligence
```

Tools: `meeting_transcribe`, `meeting_translate`, `meeting_protocol`, `meeting_process`.

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEETING_ALLOW_CLOUD` | `false` | Allow external LLM/STT |
| `MEETING_LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible server |
| `MEETING_LLM_API_KEY` | `lm-studio` | API key |
| `MEETING_LLM_MODEL` | `qwen2.5-7b-instruct` | Default LLM |
| `MEETING_MAX_FILE_MB` | `2048` | File size limit |
| `MEETING_MAX_DURATION_SEC` | `7200` | Audio/video duration limit |

## Safety

- Cloud disabled by default; external endpoints blocked unless `--allow-cloud` is set.
- Validation enforces `source_quote` grounding; invalid protocols are rejected and saved as `.protocol.rejected.json`.
- No secrets are logged; audit metadata is captured for each run.

## Test

```bash
pytest -q
```

## Artifacts

Current wheel: `dist/meeting_intelligence-0.5.0-py3-none-any.whl`
SHA256: `05a67b4b25d9edb455a2cd01c3b3886a7eae58e404ff063f0c256f87044ae244`

## License

MIT
