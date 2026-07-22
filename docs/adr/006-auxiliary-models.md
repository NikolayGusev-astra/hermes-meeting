# ADR-006: Auxiliary models per modality

**Status:** proposed  
**Date:** 2026-07-22

## Context

Сейчас `meeting process` — монолитный пайплайн: Whisper → Qwen → DOCX. Это неправильно. У агента уже есть сильная модель (deepseek-v4-pro, claude-sonnet-4). Не нужно гонять слабую локальную LLM для аналитики, когда агент может сделать это лучше.

Но у агента нет специализированных возможностей: он не умеет транскрибировать аудио (нужен Whisper), не умеет разделять голоса (нужен pyannone), не умеет делать OCR (нужен Tesseract). 

## Decision

**Агент как оркестратор auxiliary моделей по модальности.**

```
Вход (audio/video/text/image)
  │
  ▼
Агент определяет модальность
  │
  ├─ audio/video → Whisper (локально, fast) → transcript
  ├─ voice diarization → pyannone (локально, опционально) → speaker embeddings
  ├─ image/scan → Tesseract/vision-model (локально/cloud) → text
  ├─ text → MAIN AGENT MODEL → analysis + protocol
  │
  ▼
Агент обогащает (MCP: Jira, Confluence, Email, Calendar)
  │
  ▼
Протокол + задачи + рассылка
```

**Модели по модальности:**

| Модальность | Auxiliary Model | Где | Когда |
|-------------|-----------------|-----|-------|
| Speech-to-Text | `faster-whisper` (small/medium/large-v3) | Локально | Всегда |
| Speaker diarization | `pyannote.audio` (spkrec-ecapa) | Локально | `[diarization]` extras |
| OCR / handwriting | `tesseract` / cloud vision | Локально / cloud | `[ocr]` extras |
| Translation | `MEETING_TRANSLATE_MODEL` (любая LLM) | Где настроено | `--target-lang` |
| Text → Protocol | **MAIN AGENT MODEL** (deepseek-v4-pro, etc.) | Где работает агент | Всегда |
| Verification pass | `MEETING_VERIFY_MODEL` | Где настроено | Опционально |

**Конфигурация — всё через env vars:**

```bash
# STT model
MEETING_TRANSCRIBE_MODEL=large-v3

# Diarization (requires [diarization] extras)
MEETING_DIARIZATION_MODEL=pyannote/speaker-diarization-3.1

# Main analysis — uses agent's own model, not configured here

# Optional verification by stronger model
MEETING_VERIFY_MODEL=openrouter/deepseek/deepseek-chat
MEETING_VERIFY_BASE_URL=https://openrouter.ai/api/v1
MEETING_VERIFY_API_KEY=sk-or-...
```

## Consequences

- **+** Каждая модальность — своя специализированная модель. Нет компромиссов.
- **+** Агент использует свой мозг для аналитики — качество протокола растёт с моделью агента.
- **+** Плагин остаётся тонким: только STT + препроцессинг. Логика анализа — в SKILL.md.
- **+** Auxiliary модели опциональны: нет pyannone — нет диаризации, работает fallback.
- **−** Требует координации: агент должен знать какие модели доступны и роутить запросы.
