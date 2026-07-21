---
name: meeting-intelligence
description: "Local-first meeting intelligence: video/audio -> timestamped transcript -> translated transcript -> validated meeting protocol. Portable across macOS, Windows, Linux."
version: 0.5.0
author: Nikolay Gusev
license: MIT
platforms: [macos, windows, linux]
tags:
  - meetings
  - transcription
  - translation
  - protocol
  - local-first
  - hermesskill
when_to_use: "Use when the user uploads or references meeting audio/video/transcript and needs a trust-minimized transcript, translation, or protocol."
counter_triggers: "Do not use when the user only needs a quick summary from a short clip and a full pipeline would be overkill."
metadata:
  hermes:
    config:
      - name: MEETING_ALLOW_CLOUD
        prompt: Enable external LLM/STT for this run only
        required_for: Cloud fallback policy
      - name: MEETING_LLM_BASE_URL
        prompt: OpenAI-compatible local server base URL
        required_for: Translation and protocol extraction
required_environment_variables:
  - name: MEETING_LLM_API_KEY
    prompt: API key for the local LLM server
    required_for: Translation and protocol extraction
---

# Meeting Intelligence

## Setup
Install once:
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## CLI
Run from the skill directory:
```bash
python "${HERMES_SKILL_DIR}/scripts/meeting_cli.py" process /path/to/meeting.mp4 --model small --language en --device cpu --target-lang ru
```

Subcommands:
- `transcribe SOURCE`
- `translate TRANSCRIPT`
- `protocol TRANSCRIPT`
- `process SOURCE`

## Environment
- `MEETING_LLM_BASE_URL` — OpenAI-compatible local server
- `MEETING_LLM_API_KEY` — API key
- `MEETING_LLM_MODEL` — default `qwen2.5-7b-instruct`
- `MEETING_ALLOW_CLOUD` — default `false`; external endpoints are blocked unless explicitly enabled via `--allow-cloud`
