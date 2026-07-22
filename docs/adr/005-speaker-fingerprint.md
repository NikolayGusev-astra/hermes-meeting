# ADR-005: Speaker voice fingerprint for reliable attribution

**Status:** proposed  
**Date:** 2026-07-22

## Context

Проблема: диаризация разделяет голоса (SPEAKER_00, SPEAKER_01), но не идентифицирует людей. Сегодня пользователь вручную мапит через `--participants`. Но для постоянной команды (Николай, Алексей, Евгений) это нужно автоматизировать. Идея: «отпечаток человека» — voice embedding, который сохраняется один раз и используется для автоматической атрибуции во всех последующих встречах.

## Decision

**Speaker fingerprint via pyannote embedding + local DB.**

### Как это работает

1. **Enrollment (один раз):**
   ```
   meeting enroll --name "Николай" --audio николай_30сек.wav
   ```
   → pyannote извлекает speaker embedding (256-float вектор) → сохраняет в `~/.meeting/speakers/николай.embedding`

2. **Attribution (каждая встреча):**
   ```
   meeting process встреча.mp4
   ```
   → pyannote диаризация → для каждого SPEAKER_NN извлекается embedding → cos-distance до всех сохранённых → ближайший > порога (0.75) → авто-атрибуция

3. **Fallback:**
   - Нет сохранённых отпечатков → `--participants` ручной маппинг (как сейчас)
   - Новый спикер → метка `SPEAKER_NN (unknown)`, пользователь может `meeting enroll` потом
   - Низкая уверенность → warning в протоколе, просит подтверждения

### Структура данных

```
~/.meeting/
  speakers/
    николай.embedding    # 256 float32 = 1KB
    алексей.embedding
    евгений.embedding
  sessions/
    2026-07-22/
      embeddings.json     # SPEAKER_00 → embedding из этой встречи
```

### Почему не облако

- Embedding-модель pyannote/spkrec-ecapa-voxceleb работает локально, ~20MB
- Cosine distance вычисляется за микросекунды
- Никакие голосовые данные не покидают машину
- Не нужен GPU — CPU inference <1 сек на 30-секундный клип

## Consequences

- **+** Один раз записал 30 сек → все будущие встречи атрибутируются автоматически
- **+** Локально, без облака, без API-ключей
- **+** 1KB на человека — можно хранить в git (если не секретно)
- **+** Fallback на ручной `--participants` если отпечатков нет
- **−** Требует `[diarization]` extras (pyannote)
- **−** Точность зависит от качества записи (шум, микрофон)
- **−** Не работает, если человек говорит другим голосом (болезнь)
- **−** Нужен enrollment-клип для каждого нового участника

## Альтернативы (отклонены)

- **Speaker recognition API (Azure, AWS)** — деньги, облако, привязка к вендору
- **LLM-based**: просить LLM угадать кто говорит по контексту — ненадёжно, галлюцинации
- **Ручной всегда** — не масштабируется
