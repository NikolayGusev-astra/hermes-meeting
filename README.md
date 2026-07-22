# Meeting Intelligence

Local-first meeting processing: audio/video → timestamped transcript → translation → validated meeting protocol.

Optional Hermes plugin integration via `meeting-intelligence`.

## Install / Установка

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install .
```

Or install from wheel:

```bash
pip install dist/meeting_intelligence-0.6.0-py3-none-any.whl
```

## Quick Start / Быстрый старт

```bash
pip install '.[local]'                    # LM Studio / локальный режим (по умолчанию)
# pip install '.[diarization]'            # optional speaker diarization / опциональная диаризация
```

Set one backend / Выберите один backend:

```bash
# LM Studio (default) / LM Studio (по умолчанию)
export MEETING_LLM_BASE_URL=http://localhost:1234/v1
export MEETING_LLM_API_KEY=lm-studio
export MEETING_LLM_MODEL=qwen2.5-7b-instruct

# Ollama / Ollama
export MEETING_LLM_BASE_URL=http://localhost:11434/v1
export MEETING_LLM_API_KEY=ollama
export MEETING_LLM_MODEL=llama3.1

# llama.cpp server / сервер llama.cpp
export MEETING_LLM_BASE_URL=http://localhost:8080/v1
export MEETING_LLM_API_KEY=llama.cpp
export MEETING_LLM_MODEL=local-model

# OpenAI cloud / облако OpenAI
export MEETING_ALLOW_CLOUD=true
export MEETING_LLM_BASE_URL=https://api.openai.com/v1
export MEETING_LLM_API_KEY="$OPENAI_API_KEY"
export MEETING_LLM_MODEL=gpt-4o-mini

# Verify / Проверка
meeting --help
```

PowerShell: replace `export NAME=value` with `$env:NAME = "value"`.

## CLI / CLI

```bash
# English
meeting transcribe /path/to/meeting.mp4 --model small --language en --device cpu
meeting translate /path/to/meeting.transcript.txt --target-lang ru --allow-cloud
meeting protocol /path/to/meeting.transcript.txt --model qwen2.5-7b-instruct
meeting process /path/to/meeting.mp4 --language en --target-lang ru --docx

# Русский
meeting transcribe /path/to/meeting.mp4 --model small --language en --device cpu
meeting translate /path/to/meeting.transcript.txt --target-lang ru --allow-cloud
meeting protocol /path/to/meeting.transcript.txt --model qwen2.5-7b-instruct
meeting process /path/to/meeting.mp4 --language en --target-lang ru --docx
```

Alternative module invocation:

```bash
python -m meeting_intelligence transcribe /path/to/meeting.mp4
```

Subcommands:
- `transcribe SOURCE` — extract timestamped transcript
- `translate TRANSCRIPT` — translate transcript lines
- `protocol TRANSCRIPT` — extract validated meeting protocol
- `process SOURCE` — full pipeline: transcribe → translate → protocol

## Hermes plugin / Плагин Hermes

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

| Variable | Default | EN | RU |
|----------|---------|----|----|
| `MEETING_ALLOW_CLOUD` | `false` | Allow external LLM/STT | Разрешить внешний LLM/STT |
| `MEETING_LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible server | OpenAI-совместимый сервер |
| `MEETING_LLM_API_KEY` | `lm-studio` | API key | Ключ API |
| `MEETING_LLM_MODEL` | `qwen2.5-7b-instruct` | Default LLM | Модель LLM по умолчанию |
| `MEETING_TRANSCRIBE_MODEL` | `small` | Whisper model | Модель Whisper |
| `MEETING_MAX_FILE_MB` | `2048` | File size limit, MB | Лимит размера файла, МБ |
| `MEETING_MAX_DURATION_SEC` | `7200` | Audio/video duration limit, sec | Лимит длительности аудио/видео, сек |

## Safety / Безопасность

- Cloud disabled by default; external endpoints blocked unless `--allow-cloud` is set. / Облако отключено по умолчанию; внешние endpoint блокируются, если не указан `--allow-cloud`.
- Validation enforces `source_quote` grounding; invalid protocols are rejected and saved as `.protocol.rejected.json`. / Валидация проверяет `source_quote`; невалидные протоколы отклоняются и сохраняются как `.protocol.rejected.json`.
- No secrets are logged; audit metadata is captured for each run. / Секреты не логируются; для каждого запуска сохраняется audit metadata.

## Test / Тестирование

```bash
pytest -q
```

## Artifacts / Артефакты

Current wheel: `dist/meeting_intelligence-0.6.0-py3-none-any.whl`
SHA256: `5eb34667f0185369bfc48f8b8067f0424c4acfa5c1994ff2d37e7739ca1a5953`

## License

MIT
