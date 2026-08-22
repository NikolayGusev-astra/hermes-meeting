# План: Telegram post media source (t.me/<channel>/<id>) — ADR-011

**Дата:** 2026-08-22 · **Автор:** Rin (agent) · **Статус:** на утверждение
**Триггер:** https://t.me/neuraldeep/2288 — пост с видео (стрим 2ч15м),
сейчас плагин такой источник не умеет.

---

## 1. Проблема

`_is_tg_source()` в `sources.py` считает **любую** ссылку с `t.me` источником
диалога (`tg:<handle>`). Ссылка на конкретный пост `t.me/<channel>/<post_id>`
(или пересланное сообщение) попадает в `resolve_tg_source()` и запускает
скачивание **всех голосовых диалога** — не то, что хочет пользователь, указавший
конкретный пост. Отдельного пути «медиа одного поста» нет.

## 2. Цель

`t.me/<channel>/<numeric_id>` → скачать вложение этого сообщения
(видео / документ-аудио / голосовое / круглое видео) и подать в обычный
пайплайн как локальный файл. Диаризация и протокол — без изменений.
Формат `tg:<handle>` (инжест диалога) остаётся как есть.

## 3. Дизайн

### 3.1 Маршрутизация в `sources.py`

```python
_TG_POST_RE = re.compile(r"(?:^tg:|^https?://t\.me/)(?P<channel>[A-Za-z0-9_]+)/(?P<post>\d+)$")

def _parse_tg_post(source: str) -> tuple[str, int] | None:
    """'t.me/foo/2288' или 'tg:foo/2288' → ('foo', 2288); иначе None."""
```

В `_is_tg_source()`: если `_parse_tg_post()` вернула совпадение — это НЕ диалог,
маршрут в новый `resolve_tg_post_media()` (см. 3.3). Проверку поста делаем
**до** проверки диалога.

### 3.2 Точка входа в pipeline

В `transcribe()` (pipeline.py): перед веткой `ingest_telegram` —

```python
parsed = _parse_tg_post(params.source)
if parsed:
    path = resolve_tg_post_media(parsed[0], parsed[1], output_dir=...)
    # дальше локальный файл идёт через check_resource_limits + extract_audio как URL-ветка
```

### 3.3 `resolve_tg_post_media(channel, post_id, output_dir) -> Path`

Telethon (lazy import, та же сессия/прокси что ADR-010):

1. `client.get_entity(channel)` → `client.get_messages(entity, ids=post_id)`
2. Сообщение без медиа → `fail("Message <id> in <channel> has no media")`.
3. Выбор файла:
   - `msg.video` (в т.ч. round) / `msg.document` (audio/document) →
     `client.download_media(msg, file=...)`
4. Имя файла: `<channel>_<post_id>.<ext>` (ext из mime_type атрибутов).
5. Возврат Path → обычный конвейер (лимиты/ffmpeg/whisper).

Не тянем новые зависимости; telethon уже optional `[tg]`.

### 3.4 CLI/MCP

Новых флагов не нужно: `transcribe "https://t.me/neuraldeep/2288" --diarize`
просто заработает. MCP `meeting_transcribe(source=...)` тоже.

## 4. Тесты (TDD, офлайн)

`tests/unit/test_tg_post_source.py`, стиль — как `test_sources_proxy.py` /
`test_telegram_ingest.py`:

1. `test_parse_tg_post_matches` — матрица URL:
   да: `t.me/neuraldeep/2288`, `https://t.me/neuraldeep/2288`,
   `tg:neuraldeep/2288`, `t.me/c/1234567/2288` (приватный — отдельный кейс, см. §6);
   нет: `t.me/neuraldeep`, `tg:neuraldeep`, обычные URL, пустая строка.
2. `test_is_tg_source_dialog_not_post` — `_is_tg_source("t.me/neuraldeep/2288")`
   остаётся True (это всё ещё tg), но роутинг уходит в post-media.
3. `test_resolve_tg_post_media_download` — фейковое сообщение
   (`SimpleNamespace(video=..., _client=None)`), `_download_voice`-подобная
   заглушка пишет байты → возвращается существующий Path.
4. `test_resolve_tg_post_no_media_fails` — msg.media is None → MeetingError/SystemExit.
5. `test_pipeline_routes_tg_post_to_local_file` — monkeypatch
   `resolve_tg_post_media` → tmp wav; проверить, что `transcribe()` уходит в
   файловую ветку, а не в `ingest_telegram`.

## 5. Шаги

| # | Шаг | Артефакт |
|---|-----|----------|
| 1 | Утверждение плана | этот файл |
| 2 | RED: тесты §4 падают | `tests/unit/test_tg_post_source.py` |
| 3 | GREEN: `_parse_tg_post` + `resolve_tg_post_media` + роутинг | sources.py, pipeline.py |
| 4 | Полный юнит-прогон | pytest -q зелёный |
| 5 | Реальный кейс | `transcribe t.me/neuraldeep/2288` → транскрипт |
| 6 | ADR-011 + commit | docs/adr/011-tg-post-media.md |

Push — не делаем (как обычно, только по просьбе).

## 6. Риски / открытые вопросы

- **Приватные ссылки** `t.me/c/<chat_id>/<post>`: chat_id отрицательный,
  резолв через `get_entity(PeerChat(...))`. В scope v1 НЕ включаем — только
  публичные каналы (наш кейс neuraldeep — публичный). Задокументируем.
- **Большое видео**: 2ч+ стрим в TG может быть >2ГБ; лимит
  `MEETING_MAX_FILE_MB` (дефолт 2048) может уронить шаг — это корректное
  поведение, юзер поднимает лимит env-ом. Для нейралдипа есть YouTube-зеркало.
- **Альбомы**: сообщение с группой медиа — берём первый видеофайл; если
  понадобится «все части» — отдельная задача.
