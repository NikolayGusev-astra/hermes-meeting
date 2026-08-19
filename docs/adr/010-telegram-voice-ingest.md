# ADR-010: Telegram voice ingest (фича «Встречи»)

**Status:** proposed  \
**Date:** 2026-08-20  \
**Deciders:** Николай (user), Rin (agent)  \
**Related:** [001-stt-model](adr/001-stt-model.md), [002-diarization](adr/002-diarization.md),
[005-speaker-fingerprint](adr/005-speaker-fingerprint.md),
`docs/plans/telegram-voice-ingest.md`

---

## Context

Плагин `meeting-intelligence` принимает на вход локальный файл или URL
(`sources.py` → yt-dlp). Пользователь вручную скачивает голосовые из Telegram
сторонним скриптом и кидает в пайплайн. Хочется автоматизации: по ссылке/юзернейму
на диалог подтянуть все голосовые через настроенный **локальный Telethon-userbot**
и сразу получить расшифровку, сгруппированную по встречам.

Ключевой инсайт, изменивший дизайн против изначального плана
(`telegram-voice-ingest.md`): **в личном диалоге отправитель каждого войса
известен из метаданных Telegram** (`Message.out` / `Message.sender_id`), а не из
акустических признаков. То есть для DM атрибуция спикера = реальный sender, что
**точнее** pyannote/voiceprint (которые нужны только в группах, где говорит
несколько неизвестных). Диаризация по паузам (`_silence_speakers`) для DM тоже
избыточна — войс это одна реплика одного человека.

Второй инсайт: «встреча» = один день общения (по умолчанию), но границы сессий
внутри дня стоит уточнять анализом временных разрывов между войсами, а не
слепо склеивать всё за день.

---

## Decision

1. **Новый источник `tg:`** в `sources.py` рядом с yt-dlp.
   `resolve_tg_source(handle: str, since=None, limit=3000) -> list[Path]`.
   - Lazy-import `telethon` (как yt-dlp сейчас — не тянем зависимость в ядро).
   - Проверка наличия userbot-сессии (`~/.hermes/tg-userbot/session_fixed`);
     если нет — `fail("Telegram ingest requires a local userbot session")`.
   - Прокси через `MEETING_YT_PROXY` (SOCKS5, как остальные источники).
   - Фильтр: только `Message.voice` и `Video.round_message`.
   - Возвращает список скачанных `.ogg` (имя `<msg_id>_<YYYYMMDD_HHMMSS>.ogg`).

2. **Атрибуция спикера = sender для DM**, реальный voiceprint/pyannote для групп.
   - В `transcribe_audio` добавляется опц. параметр `speaker_label: str | None`.
     Если передан (из TG-метаданных) — строка транскрипта несёт его,
     диаризация НЕ запускается.
   - Для групп (`peer channel/group`) — поведение как сейчас (`--diarize`
     `--recognize` через pyannote/voiceprints).
   - В личке: `msg.out == True` → «Николай» (владелец сессии),
     иначе → `msg.sender.first_name` / username. «Владелец» резолвится один раз
     через `client.get_me()`.

3. **Группировка по встречам** — новый модуль `ingest.py` (в пакете
   `meeting_intelligence`), НЕ в `transcribe.py`:
   - Кластеризация войсов: день как база + разрыв > `GAP_MINUTES` (def 120)
     внутри дня = новая сессия.
   - Результат — объект `Meeting` (папка + метаданные), содержащий `Utterance[]`.
   - Соблюдает `NAMING.md`: папка `{YYYY-MM-DD}_встреча_<тема>`.

4. **CLI + MCP — как в плагине сейчас** (зеркально `meeting_transcribe`):
   - CLI: `meeting transcribe tg:Evgenius_Morozov` — источник `tg:` резолвится
     в `transcribe()` как локальный путь (ветка в `_resolve_source`).
   - MCP: `meeting_transcribe` уже принимает `source: str` → `tg:` просто
     пройдёт через тот же путь. Доп. опции `since`/`limit` — опц. поля
     `TranscribeParams` (дефолты = старое поведение, обратная совместимость).
   - Новый тул `meeting_ingest_telegram(handle, since?, limit?)` НЕ добавляем —
     дублирует `meeting_transcribe`; источник `tg:` покрывает случай.

5. **Userbot-only** (by design, приватность, no-bot-token). Бот не имеет доступа
   к чужим войсам в личке. Pin `telethon==1.42.0` (сессия чувствительна к версии:
   schema mismatch → `ValueError: too many values to unpack`).

---

## Consequences

- **+** Автоматизация: одна команда вместо ручного скачивания + расшифровки.
- **+** Точная атрибуция в DM (sender из метаданных) — лучше чем voiceprint.
- **+** Reuse всего STT/диаризационного стека — ничего не переписываем.
- **+** Обратная совместимость: `transcribe`/`process`/`protocol` без `tg:` работают
  как раньше (дефолты `TranscribeParams` не меняются).
- **−** Зависимость от userbot-сессии: без неё фича недоступна (это ок, by design).
- **−** telethon не в core-зависимостях — lazy import + документация в INSTALL.md.
- **−** Rate-limit Telegram при сотнях сообщений → нужен backoff в `resolve_tg_source`.
- **−** Рантайм транскрибации: рабочий путь = Hermes venv + `PYTHONPATH=src`
  (системный Python без `ctranslate2`/CUDA12 DLL). Зафиксировать в docs/CI.

---

## Alternatives considered

- **Бот вместо userbot** — отпадает: бот не читает войсы из чужих личных диалогов
  владельца, только из своих групп. Userbot = сессия владельца.
- **Полноценная сущность «Встреча» как кросс-файловый агрегат** (несколько войсов
  из разных дней = одна встреча) — отложено: сложнее, выигрыш неочевиден. День =
  встреча по умолчанию покрывает 90% кейсов (переписка с Евгением: 17 войсов /
  4 дня).
- **Замена Whisper на text-normalizer (s1-mini)** — отпадает: English-only, не
  применимо к RU (см. обсуждение в чате, ADR-001).
