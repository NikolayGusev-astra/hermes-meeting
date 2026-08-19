# Plan: Telegram Voice Ingest

**Feature plan** — скачивание голосовых из Telegram через userbot и их расшифровка  \
**Date:** 2026-08-20  \
**Status:** Proposed  \
**Related:** `docs/adr/001-stt-model.md`, `docs/NAMING.md`

---

## 1. Motivation

Пользователь хранит рабочие голосовые сообщения в личках/чатах Telegram
(реальный кейс: переписка с `@Evgenius_Morozov`, ~17 голосовых / 8.4 мин / 10 МБ
за август 2026). Сейчас плагин умеет расшифровывать только локальные файлы
(`meeting transcribe <path>`). Чтобы получить расшифровку, пользователь вручную
скачивает войсы сторонним скриптом и кидает в пайплайн.

Цель: дать одну команду, которая по ссылке/юзернейму тянет все голосовые из
указанного диалога через локальный Telethon-userbot и сразу готовит
расшифровку, сгруппированную по датам и темам.

Это расширяет существующий источник-загрузчик (`sources.py`, где уже есть
yt-dlp для URL) на нативный Telegram-источник — без выхода за рамки локального
userbot-сессии (приватность, no-cloud).

---

## 2. Scope

In scope:
- Новый CLI-источник `tg:` для `meeting transcribe`.
- Скачивание **только** голосовых (`Message.voice`) и round-видео (`Video.round_message`)
  из указанного диалога.
- Расшифровка каждого файла через существующий `transcribe_audio` (Whisper/
  CTranslate2, GPU `large-v3-turbo`, `--language ru`).
- Сборка сводного вывода, сгруппированного по дате и теме (reuse `NAMING.md`
  + существующая логика content-type detection).

Out of scope (этот план):
- Скачивание текстовых сообщений, медиа, стикеров.
- Диаризация по собеседникам внутри одного личного диалога (в 1:1 нет смысла;
  `--recognize` по voiceprint оставляем опц. для групп).
- Замена Whisper на text-normalizer (см. ADR 001; `s1-mini` — English-only,
  не применимо к RU-контенту).

---

## 3. CLI contract

```bash
# По username / ссылке / id диалога
meeting transcribe tg:Evgenius_Morozov
meeting transcribe "https://t.me/Evgenius_Morozov"
meeting transcribe tg:123456789                      # numeric chat id

# Опции (наследуются от transcribe)
  --language ru            # обязательно для RU, как в текущем пайплайне
  --device cuda --compute-type float16
  --since 2026-08-01       # опционально: окно по дате
  --limit 3000             # лимит сообщений при сканировании
  --diarize / --recognize  # только для групповых чатов
  --output <dir>           # куда сложить .ogg + .transcript.txt
```

Поведение:
1. Резолвим `tg:<handle>` → `get_entity` через userbot-сессию.
2. Итерируем `client.iter_messages`, фильтруем голосовые.
3. Качаем в `<output>/<msg_id>_<YYYYMMDD_HHMMSS>.ogg`.
4. Для каждого — `transcribe_audio(..., language="ru")`.
5. Формируем сводку по датам (см. раздел 5).

---

## 4. Implementation

### 4.1 `src/meeting_intelligence/sources.py`
Добавить `resolve_tg_source(handle: str) -> list[Path]` рядом с
`resolve_source` (yt-dlp). Логика:
- Проверить наличие userbot-сессии (`~/.hermes/tg-userbot/session_fixed`).
  Если нет — `fail("Telegram ingest requires a local userbot session")`.
- Импортировать `telethon` лениво (`find_spec` как у yt-dlp, чтобы не тянуть
  зависимость в основной пайплайн).
- Проксировать через `MEETING_YT_PROXY` (SOCKS5), как остальные источники.
- Вернуть список путей к скачанным `.ogg`.

### 4.2 `src/meeting_intelligence/cli.py`
В `transcribe` subparser: `source` уже принимает строку. Добавить ветку —
если `source.startswith("tg:")` или это `t.me`-ссылка →
`resolve_tg_source` → получить список файлов → для каждого вызвать
существующий `transcribe_audio`. Не дублировать логику транскрибации.

### 4.3 Reuse (НЕ писать заново)
- `transcribe_audio` — уже умеет OGG/Opus через ffmpeg + Whisper.
- `MEETING_TRANSCRIBE_*` env-флаги и GPU-автодетект — наследуются.
- `NAMING.md` — правила именования папок `{date}_{type}_{topic}`.
- Whisper garbage filter (`_clean_whisper_artifacts`) — уже в пайплайне.

---

## 5. Группировка по датам и темам

После расшифровки каждого войса получаем `meta` с датой сообщения.
Сводный вывод (`meeting agent-transcript` или отдельный `--summary`):
- Группировка по дню (`YYYY-MM-DD`).
- Внутри дня — блоки по темам: тему берём из первых ~30с транскрипта
  (как в текущем NAMING-правиле) либо кластеризуем по близости во времени
  (сообщения в рамках одного часа = одна сессия).
- Итог: папка `2026-08-19_встреча_Evgenius/` с файлами
  `<HHMMSS>.transcript.txt` + `Саммари.docx` (через `generate-docx`).

---

## 6. Ограничения и риски

- **Userbot-only.** Без `session_fixed` команда не работает — это by design
  (приватность, no-bot-token). Бот не имеет доступа к чужим войсам в личке.
- **Telethon-версия.** Сессия чувствительна к версии (см. skill
  `local-telegram-userbot`: schema mismatch → `ValueError: too many values to
  unpack`). Pin `telethon==1.42.0`.
- **Rate-limit Telegram.** Скачивание 17 файлов — ок; на сотнях сообщений
  нужен `sleep` между `download_media`. Добавить backoff.
- **Язык.** Всегда `--language ru`; auto-detect для RU ненадёжен (ADR 001).
- **VRAM.** На GPU 6–8 ГБ `large-v3-turbo` (~1.6 ГБ) + пайплайн — влезает, но
  рядом не должен висеть LM Studio (см. TROUBLESHOOTING, GPU VRAM pre-check).

---

## 7. Verification

- [ ] `meeting transcribe tg:Evgenius_Morozov --language ru --device cuda`
      скачивает N войсов, каждый расшифровывает, кладёт `.ogg`+`.transcript.txt`.
- [ ] При отсутствии сессии — понятная ошибка, не падает с traceback.
- [ ] Группировка по датам совпадает с датами сообщений в Telegram.
- [ ] `--since` корректно отсекает старые сообщения.
- [ ] `NAMING.md` соблюдён (русские имена файлов/папок).
- [ ] Тест: mock telethon → проверить фильтрацию (только voice/round,
      не текст/фото).
