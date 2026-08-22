# ADR-011: Telegram post media source (`t.me/<channel>/<id>`)

**Status:** accepted (реализовано 2026-08-22)
**Date:** 2026-08-22
**Deciders:** Николай (user), Rin (agent)
**Related:** [010-telegram-voice-ingest](adr/010-telegram-voice-ingest.md),
`docs/plans/tg-post-media-source.md`

---

## Context

ADR-010 добавил источник `tg:<handle>` — инжест **всех голосовых диалога**
через локальный userbot. Маршрутизация в `sources.py` построена на
`_is_tg_source()`: любая строка с `t.me` считается диалогом.

Практика показала второй сценарий: пользователь кидает ссылку на **конкретный
пост** с медиа (пример: `t.me/neuraldeep/2288` — запись стрима «Как писать код
с AI-агентами?», видео ~2ч11м). Сейчас такая ссылка уходит в
`resolve_tg_source()` и начинает скачивать голосовые всего канала — не то,
что просили.

Отдельный путь «скачать вложение одного поста и подать в обычный пайплайн» в
плагине отсутствует.

## Decision

1. **Различать ссылку на пост и диалог** до проверки «это tg».
   `_parse_tg_post(source) -> tuple[channel, post_id] | None`
   матчит `tg:<channel>/<N>`, `t.me/<channel>/<N>`, `https://t.me/<channel>/<N>`
   (публичные каналы; приватные `t.me/c/<chat>/<post>` — вне scope v1).
   Совпадение → маршрут в новый резолвер, иначе поведение ADR-010 без изменений.

2. **Новый `resolve_tg_post_media(channel, post_id, output_dir) -> Path`**
   в `sources.py`:
   - та же userbot-сессия и SOCKS-прокси, что ADR-010; telethon — lazy import;
   - `get_messages(entity, ids=post_id)`; без медиа → `fail(...)`;
   - скачивание `msg.video` (вкл. round) / `msg.document`;
   - файл `<channel>_<post_id>.<ext>`; возврат Path в обычную ветку
     `transcribe()` (check_resource_limits → extract_audio → whisper).

3. **CLI/MCP без изменений**: `meeting transcribe https://t.me/neuraldeep/2288
   --diarize` просто заработает; `meeting_transcribe(source=...)` — тоже.

4. **Не делаем**: новые зависимости; инжест альбомов целиком (берём первый
   видеофайл); приватные чаты.

## Consequences

+ Ссылка на пост = один файл = обычная расшифровка/протокол, вся существующая
  логика (диаризация, voiceprints, протокол) переиспользуется как есть.
+ Инжест диалогов не меняется (обратная совместимость тестов ADR-010).
− Лимит `MEETING_MAX_FILE_MB` (дефолт 2048) может отсечь очень большое видео —
  осознанно, поднимается env-ом; для длинных стримов остаётся YouTube-зеркало.
− Приватные посты потребуют отдельного решения (PeerChat/PeerChannel резолв).

## Verification

Офлайн-тесты `tests/unit/test_tg_post_source.py` (матрица парсера, роутинг
pipeline, download/no-media на фейковых сообщениях) + живой прогон
`t.me/neuraldeep/2288`. Детали шагов — в плане
`docs/plans/tg-post-media-source.md`.
