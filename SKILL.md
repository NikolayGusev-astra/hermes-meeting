---
name: meeting-intelligence
description: "Hermes meeting-intelligence tools for local-first transcription, translation, and evidence-grounded meeting protocols. Use for meeting audio/video or timestamped transcripts when a transcript, translation, protocol, decisions, assignments, or open questions is required."
version: 0.6.0
when_to_use:
  - "Audio/video -> timestamped transcript; transcript -> translation or protocol."
  - "Need evidence-grounded decisions, assignments, participants, or open questions."
counter_triggers:
  - "Do not use for a casual summary of text with no meeting artifact or evidence requirement."
  - "Do not infer speaker identities, commitments, dates, or decisions absent from the source."
required_env:
  - MEETING_LLM_BASE_URL
  - MEETING_LLM_API_KEY
  - MEETING_LLM_MODEL
---

# Meeting Intelligence / Аналитика встреч

Install / Установка:

```bash
pip install 'meeting-intelligence[local]'  # local STT/LLM / локальные STT/LLM
pip install 'meeting-intelligence[cloud]'  # cloud client / облачный клиент
```

## Tools / Инструменты

All tools return a JSON envelope: `{"exit_code": int, "stdout": string, "stderr": string}`. `exit_code: 0` means success; `3` means the protocol failed quality gates. Outputs are files; paths below are defaults. / Все инструменты возвращают JSON-конверт; результаты сохраняются в файлы.

| Tool | Inputs / Вход | Output / Выход |
|---|---|---|
| `meeting_transcribe` | `source` (required), `model=small`, `language=en`, `device=cpu|cuda`, `compute_type=int8`, `output?` | `<source>.transcript.txt`; `<source>.transcript.json` with `source_hash`, `stt_model`, `language`, `language_probability`, `no_speech_prob`, `duration`, `segment_count`. Lines: `[start->end] SPEAKER_nn | text`. |
| `meeting_translate` | `transcript` (required), `target_lang=ru`, `allow_cloud=false`, `output?` | `<transcript>.translated.txt`; preserves timestamps and `SPEAKER_nn` prefixes. |
| `meeting_protocol` | `transcript` (required), `model=qwen2.5-7b-instruct`, `allow_cloud=false`, `docx=false`, `output?` | Valid: `<transcript>.protocol.json` (optional `.protocol.docx`); invalid: `.protocol.rejected.json`. JSON: `participants`, `agenda`, `decisions`, `assignments`, `open_questions`, `unclear`, metadata, `quality`. |
| `meeting_process` | `source` (required), `stt_model=small`, `llm_model=qwen2.5-7b-instruct`, `language=en`, `device=cpu|cuda`, `compute_type=int8`, `target_lang=ru`, `skip_translate=false`, `docx=false`, `allow_cloud=false` | Transcript + metadata, optional translation, and validated protocol as above. |

## Quality gates / Контроль качества

- Require `source_quote` for every participant, decision, and assignment; normalize whitespace and verify that the quote is grounded in the transcript. Missing or ungrounded evidence rejects the protocol.
- Set `quality.overall_confidence`: `90` when valid without warnings, `70` when warnings exist, `25` when validation errors exist; include `quality.valid`, `errors`, and `warnings`.
- No hallucination / Без галлюцинаций: extract only explicit source statements. If an assignee is absent use `unknown`; if a deadline is absent use `not_set`; place ambiguity in `unclear`.
- Speaker attribution / Атрибуция: `SPEAKER_nn` is a silence-gap heuristic, not a verified identity. Preserve labels; never map one to a person or merge speakers unless the transcript explicitly establishes it.

## LLM backends and safety / Бэкенды и безопасность

Configure every LLM backend with `MEETING_LLM_BASE_URL`, `MEETING_LLM_API_KEY`, and `MEETING_LLM_MODEL`.

| Backend | `MEETING_LLM_BASE_URL` |
|---|---|
| LM Studio (default) | `http://localhost:1234/v1` |
| Ollama | `http://localhost:11434/v1` |
| llama.cpp | `http://localhost:8080/v1` |
| Cloud OpenAI | `https://api.openai.com/v1` |

Cloud is disabled by default / Облако отключено по умолчанию. A non-loopback endpoint requires `allow_cloud=true` for the tool call; do not enable it implicitly.

## Environment / Переменные окружения

| Variable | Default | Meaning / Назначение |
|---|---|---|
| `MEETING_LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible LLM endpoint / endpoint LLM. |
| `MEETING_LLM_API_KEY` | `lm-studio` | LLM API key; use the cloud key for Cloud OpenAI. |
| `MEETING_LLM_MODEL` | `qwen2.5-7b-instruct` | Default LLM model / модель по умолчанию. |
| `MEETING_MAX_FILE_MB` | `2048` | Maximum input size / максимальный размер. |
| `MEETING_MAX_DURATION_SEC` | `7200` | Maximum media duration / максимальная длительность. |
| `MEETING_TRANSCRIBE_MODEL` | `small` | Default Whisper model / модель Whisper. |
| `MEETING_TRANSCRIBE_DEVICE` | `cpu` | Default STT device / устройство STT. |
| `MEETING_TRANSCRIBE_COMPUTE` | `int8` | STT compute type / тип вычислений STT. |
| `MEETING_TRANSCRIBE_LANG` | `en` | Default source language / язык исходника. |
| `MEETING_TRANSLATE_BATCH_SIZE` | `8` | Translation batch size / размер пакета перевода. |
