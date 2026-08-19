# SDD: Telegram Voice Ingest (фича «Встречи») v0.9.0

**Software Design Document** — автоматическое извлечение голосовых из Telegram  \
**Date:** 2026-08-20  \
**ADR:** [010](adr/010-telegram-voice-ingest.md)  \
**Related:** [001-stt-model](adr/001-stt-model.md), [002-diarization](adr/002-diarization.md),
[005-speaker-fingerprint](adr/005-speaker-fingerprint.md)

---

## 1. Domain model (data shapes first)

```python
# src/meeting_intelligence/sources.py  (новое)

@dataclass
class TgVoiceRef:
    msg_id: int
    date: datetime          # UTC, из msg.date
    sender_label: str       # "Николай" (владелец) | first_name/username
    is_out: bool            # msg.out — кто говорил
    ogg_path: Path          # скачанный файл
    duration_sec: int


# src/meeting_intelligence/ingest.py  (новый модуль)

@dataclass
class Utterance:
    msg_id: int
    date: datetime
    speaker: str            # реальный sender (из TG-метаданных)
    audio_path: Path
    transcript: str         # результат transcribe_audio
    meta: dict              # schema_version, stt_model, language, ...

@dataclass
class Meeting:
    date: date              # день встречи (UTC→локаль по желанию)
    title: str              # тема (из первых 30с / кластера)
    utterances: list[Utterance]
    folder: Path            # {YYYY-MM-DD}_встреча_<тема> (NAMING.md)

# src/meeting_intelligence/pipeline.py  (расширение TranscribeParams)
@dataclass
class TranscribeParams:
    source: str
    model: str = "small"
    language: str = "en"
    device: str = "cpu"
    compute_type: str = "int8"
    output: Optional[Path] = None
    diarize: bool = False
    num_speakers: Optional[int] = None
    recognize: bool = False
    speaker_label: Optional[str] = None   # NEW: для DM из TG-метаданных
    tg_since: Optional[str] = None         # NEW: фильтр по дате (YYYY-MM-DD)
    tg_limit: int = 3000                    # NEW: лимит сканирования
```

**Контракт обратной совместимости:** все новые поля имеют дефолты, при которых
поведение идентично текущему. Существующие вызовы `TranscribeParams(...)` без
новых полей работают без изменений.

---

## 2. Source resolution (`sources.py`)

```python
def _is_tg_source(source: str) -> bool:
    return source.startswith("tg:") or "t.me/" in source or "t.me/" in source

def resolve_tg_source(handle: str, since: str | None = None,
                      limit: int = 3000) -> list[Path]:
    """Скачать голосовые из диалога через userbot.

    Возвращает список путей к .ogg. Lazy-import telethon.
    Проверяет сессию; при её отсутствии — fail().
    Фильтрует Message.voice + Video.round_message.
    Для DM проставляет speaker_label из msg.sender (см. ADR-010 §2).
    """
```

Интеграция в `_resolve_source` (`pipeline.py`): если `source` — `tg:`,
вызвать `resolve_tg_source`, вернуть **первый** путь как основной (для
совместимости с `transcribe()`), а остальные положить в `meeting-voices-manifest.json`
рядом — чтобы `ingest.py` мог их забрать для группировки.

> Альтернатива (chosen): `meeting transcribe tg:X` расшифровывает **все** войсы
> из диалога и группирует вMeeting. Для этого `transcribe()` при `tg:`-источнике
> делегирует в `ingest_telegram()` (см. §4), а не обрабатывает один файл.

---

## 3. Speaker attribution for DM (`transcribe.py`)

```python
def transcribe_audio(
    audio: Path, model, language, device, compute_type,
    diarize=False, num_speakers=None, recognize=False,
    speaker_label=None,          # NEW
) -> Tuple[str, dict]:
    ...
    if speaker_label is not None:
        # DM: спикер известен из TG, диаризация не нужна
        enriched = [_tag_speaker(s, speaker_label) for s in segments]
        diarization_used = f"tg-sender:{speaker_label}"
    elif diarize:
        enriched = _diarize_speakers(...)   # группы, как сейчас
    else:
        enriched = _silence_speakers(segments)  # fallback, как сейчас
```

`_tag_speaker` — лёгкая обёртка: ставит `speaker_id = speaker_label` каждому
сегменту. Не трогает pyannote/voiceprints.

---

## 4. Meeting grouping (`ingest.py`, новый модуль)

```python
GAP_MINUTES = 120  # разрыв внутри дня = новая сессия

def group_into_meetings(refs: list[TgVoiceRef]) -> list[Meeting]:
    """День = база встречи; разрыв > GAP_MINUTES внутри дня = новая сессия.
    Сортировка по date. Тема = из первых 30с транскрипта (reuse NAMING-логики)
    или кластер по близости во времени.
    """

def ingest_telegram(handle: str, since=None, limit=3000,
                    language="ru", device="cuda", compute_type="float16",
                    output_dir: Path | None = None) -> list[Meeting]:
    """Полный пайплайн: resolve_tg_source → transcribe каждого →
    group_into_meetings → запись папок/файлов по NAMING.md.
    Возвращает список Meeting (без LLM-протокола — тот опц. через agent).
    """
```

Вывод соблюдает `NAMING.md`:
- Папка: `{YYYY-MM-DD}_встреча_<тема>` (русские имена).
- Внутри: `<HHMMSS>.transcript.txt` на каждый войс + `Сводный_транскрипт.md`
  сгруппированный по встречам.

---

## 5. CLI integration (`cli.py`)

Ветка в `cmd_transcribe` / `transcribe()`:
```python
if _is_tg_source(args.source):
    meetings = ingest_ingest_telegram(handle, since, limit, ...)
    # печатает сводку: N встреч, M войсов, пути
    return 0
```
Новые аргументы `transcribe` subparser: `--since YYYY-MM-DD`, `--limit N`.
Без них — поведение как сейчас (локальный файл/URL).

MCP: `meeting_transcribe(source="tg:X")` проходит через тот же путь.
Новый тул НЕ добавляем (дублирование, см. ADR-010 §4).

---

## 6. Runtime requirements (критично для CI/доков)

Рабочий путь транскрибации (выяснено эмпирически 2026-08-20):
- **Системный Python** (`Python311`): `meeting_intelligence` editable, НО
  нет `ctranslate2`/`faster_whisper`, и torch cu118 (нет CUDA12 DLL).
- **Hermes venv**: есть `faster_whisper`+`ctranslate2`+torch cu128, но пакет
  плагина не установлен.
- **Решение:** запуск через venv + `PYTHONPATH=C:/Work/hermes/meeting/src`.
  Зафиксировать в `INSTALL.md` и CI-матрице.

telethon: lazy-import, pin `==1.42.0`. Сессия: `~/.hermes/tg-userbot/session_fixed`.

---

## 7. Testing strategy (через /cursor, pstack-tdd)

- `test_sources.py`: mock telethon Client — проверить фильтрацию
  (только voice/round, не текст/фото), корректность `speaker_label` для DM
  (`msg.out`→владелец, иначе sender), скачивание в нужную папку.
- `test_ingest.py`: `group_into_meetings` на фикстуре списка `TgVoiceRef`
  (разные дни + разрыв внутри дня → проверить границы сессий).
- `test_transcribe_speaker.py`: `transcribe_audio` с `speaker_label` не
  вызывает pyannote, проставляет метку в каждой строке.
- Все тесты offline (mock Whisper/telethon), без реального TG/аудио.

RED→GREEN: тест падает до реализации, зеленеет после. Без фиктивного GREEN.
