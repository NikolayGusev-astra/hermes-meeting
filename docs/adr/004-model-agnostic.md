# ADR-004: Model-agnostic wrapper architecture

**Status:** accepted  
**Date:** 2026-07-22

## Context

Проект должен работать с любой OpenAI-совместимой LLM: LM Studio (локально), Ollama, llama.cpp, облачный OpenAI. Разные модели имеют разное качество JSON, понимание русского, склонность к галлюцинациям. Нельзя полагаться на конкретную модель для критической логики.

## Decision

**Вся логика — в обвязке, не в LLM.**

1. **Prompt engineering** — строгие JSON-схемы в системном промпте, запрет выдумывать имена, требование VERBATIM source_quotes. Единый промпт для всех моделей.

2. **JSON repair** — `_repair_json()`: исправление single quotes, trailing commas, markdown fences. Работает до передачи в парсер.

3. **Fuzzy validation** — 60% word overlap вместо exact match. Переживает мелкие перефразирования любой моделью.

4. **Chunking** — транскрипты >6000 токенов режутся на overlapping chunks. Каждый chunk обрабатывается независимо, результаты merge по source_quote dedup.

5. **Garbage filter** — удаление Whisper-артефактов до LLM, не после.

6. **`--model` флаг** — пользователь передаёт любой model ID. По умолчанию `MEETING_LLM_MODEL`.

7. **`--participants` флаг** — пост-обработка маппинга SPEAKER_NN → имена. Работает одинаково для любой LLM.

## Consequences

- **+** Смена модели не требует смены кода
- **+** Gemma, Qwen, Llama, GPT — все работают через один интерфейс
- **+** Качество держится на обвязке, модель — взаимозаменяемый компонент
- **−** Не используем model-specific фичи (structured output, function calling)
- **−** Промпт должен быть универсальным, что ограничивает оптимизацию под конкретную модель
