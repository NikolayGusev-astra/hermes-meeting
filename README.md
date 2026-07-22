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
pip install dist/meeting_intelligence-0.5.1-py3-none-any.whl
```

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

Current wheel: `dist/meeting_intelligence-0.5.1-py3-none-any.whl`
SHA256: `3f15edf29f5c6d3ca9c60937ff3a11215ecf58086eabd1bd8cd9f03530f04dac`

## License

MIT
