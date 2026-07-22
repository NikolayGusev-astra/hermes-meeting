---
name: meeting-intelligence
description: "Local-first meeting intelligence: video/audio -> timestamped transcript -> translated transcript -> validated meeting protocol. Portable across macOS, Windows, Linux."
version: 0.5.1
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

## Install / Установка

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install .
```

Or install from wheel:

```bash
pip install dist/meeting_intelligence-0.5.1-py3-none-any.whl
```

## CLI / CLI

```bash
# English
meeting transcribe meeting.mp4 --model small --language en --device cpu
meeting translate meeting.transcript.txt --target-lang ru --allow-cloud
meeting protocol meeting.transcript.txt --model qwen2.5-7b-instruct
meeting process meeting.mp4 --language en --target-lang ru --docx

# Русский
meeting transcribe meeting.mp4 --model small --language en --device cpu
meeting translate meeting.transcript.txt --target-lang ru --allow-cloud
meeting protocol meeting.transcript.txt --model qwen2.5-7b-instruct
meeting process meeting.mp4 --language en --target-lang ru --docx
```

Alternative module invocation:

```bash
python -m meeting_intelligence transcribe meeting.mp4
```

Subcommands:
- `transcribe SOURCE`
- `translate TRANSCRIPT`
- `protocol TRANSCRIPT`
- `process SOURCE`

## Hermes plugin

Register in Hermes config:

```yaml
plugins:
  enabled:
    - meeting-intelligence
```

Available tools:
- `meeting_transcribe`
- `meeting_translate`
- `meeting_protocol`
- `meeting_process`

## Environment / Переменные окружения

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEETING_ALLOW_CLOUD` | `false` | Allow external LLM/STT / Разрешить внешний LLM/STT |
| `MEETING_LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible server / OpenAI-совместимый сервер |
| `MEETING_LLM_API_KEY` | `lm-studio` | API key / Ключ API |
| `MEETING_LLM_MODEL` | `qwen2.5-7b-instruct` | Default LLM / Модель LLM по умолчанию |
| `MEETING_MAX_FILE_MB` | `2048` | File size limit / Лимит размера файла |
| `MEETING_MAX_DURATION_SEC` | `7200` | Audio/video duration limit / Лимит длительности аудио/видео |

## Safety / Безопасность

- Cloud disabled by default; external endpoints blocked unless `--allow-cloud` is set.
  / Облако отключено по умолчанию; внешние endpoint блокируются, если не указан `--allow-cloud`.
- Validation enforces `source_quote` grounding; invalid protocols are rejected and saved as `.protocol.rejected.json`.
  / Валидация проверяет `source_quote`; невалидные протоколы отклоняются и сохраняются как `.protocol.rejected.json`.
- No secrets are logged; audit metadata is captured for each run.
  / Секреты не логируются; для каждого запуска сохраняется audit metadata.

## Test / Тестирование

```bash
pytest -q
```

## Artifacts / Артефакты

Current wheel: `dist/meeting_intelligence-0.5.1-py3-none-any.whl`
SHA256: `3f15edf29f5c6d3ca9c60937ff3a11215ecf58086eabd1bd8cd9f03530f04dac`

## License

MIT
