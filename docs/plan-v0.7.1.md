# План рефакторинга meeting-intelligence v0.7.1

## P0: Разрезать cli.py на модули

**Цель:** 1233 строки → каждый модуль <200 строк

```
src/meeting_intelligence/
├── cli.py                    # ~250 строк: main(), argparse, вызов модулей
├── gpu.py                    # ~50 строк: _transcribe_default_device, cublas probe
├── language.py               # ~40 строк: Russian cue detection, _MISDETECTED_RU_PATTERNS
├── sources.py                # ~60 строк: _is_url, _resolve_source, yt-dlp download
├── transcribe.py             # ~150 строк: transcribe_audio, _clean_whisper_artifacts, _strip_segment_id
├── protocol/
│   ├── __init__.py           # re-exports
│   ├── chunk.py              # ~90 строк: chunking, _build_protocol_chunk
│   ├── extract.py            # ~80 строк: _extract_protocol, source_quote fuzzy
│   └── verify.py             # ~60 строк: _verify_protocol, _protocol_verification_enabled
├── output/
│   ├── __init__.py           # re-exports
│   ├── docx.py               # ~150 строк: _save_docx, write_summary_docx, write_analytical_docx, write_protocol_docx
│   └── json.py               # ~40 строк: prepare_agent_transcript
├── plugin/
│   └── __init__.py           # без изменений
└── __init__.py
```

## P0: Устранить дублирование DOCX-генераторов

Три функции (write_summary/analytical/protocol) дублируют:
- `path.parent.mkdir(parents=True, exist_ok=True)`
- `doc = Document()`
- `doc.save(path)` + `log.info("Saved DOCX: %s", path)`

Вынести в общий:
```python
def _save_docx(doc: Document, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    log.info("Saved DOCX: %s", path)
```

## P0: Имена файлов по NAMING.md

Сейчас: `protocol.docx`, `summary.docx` (английские)
Должно быть: `Протокол.docx`, `Саммари.docx` (русские)

Файл NAMING_MAP в `output/docx.py`:
```python
NAMES_RU = {
    "protocol": "Протокол.docx",
    "summary": "Саммари.docx",
    "analytical": "Аналитическая_записка.docx",
    "decision-register": "Реестр_решений.xlsx",
    "assignment-list": "Список_поручений.xlsx",
    "detailed-minutes": "Подробный_конспект.docx",
    "action-plan": "План_действий.docx",
    "executive-brief": "Справка.docx",
    "knowledge-article": "Статья.docx",
    "transcript": "транскрипт.txt",
}
```

## P1: Почистить pipeline от старых English-прогонов

Удалить дублирующиеся папки: `1_lecture_friday`, `2_lecture_friday`, `2026_04_09_..._group_1`.

## P1: Смержить cmd_process и cmd_transcribe

Оба вызывают `transcribe_audio()` → вынести общий `_transcribe_and_save()`.

## P1: Починить entry-point тест

Ошибка: `ModuleNotFoundError: No module named 'meeting_intelligence'` без `pip install -e .`.

## Порядок работ

1. Создать модули: `gpu.py`, `language.py`, `sources.py` — вырезать из cli.py
2. Создать `protocol/` пакет: `chunk.py`, `extract.py`, `verify.py`
3. Создать `output/` пакет: `docx.py`, `json.py`
4. Упростить cli.py: только main, argparse, вызовы модулей
5. Добавить NAMES_RU и переименовать выходы
6. Почистить pipeline
7. Починить тесты
8. 41 passed, 1 xfailed, ruff clean
