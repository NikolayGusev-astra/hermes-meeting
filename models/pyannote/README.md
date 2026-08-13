# pyannote speaker-diarization модели (offline)

Диаризационные модели для `meeting_transcribe --diarize`. Загружаются **офлайн**
(без интернета и HF-токена) через `HF_HUB_CACHE` → этот каталог.

Структура — стандартный кэш huggingface_hub (`refs/` + `snapshots/<hash>/` + `blobs/`):

| Каталог | Модель | Вес |
|---------|--------|-----|
| `models--pyannote--speaker-diarization-3.1` | пайплайн диаризации (config.yaml) | ~6 КБ |
| `models--pyannote--segmentation-3.0` | сегментация спикеров | ~5.7 МБ |
| `models--pyannote--speaker-diarization-community-1` | PLDA | ~270 КБ |
| `models--pyannote--wespeaker-voxceleb-resnet34-LM` | эмбеддинги голосов | ~26 МБ |

## Загрузка (runtime)

Код диаризации (`src/meeting_intelligence/transcribe.py`, `_diarize_speakers`)
на время загрузки пайплайна ставит:

```
HF_HUB_OFFLINE=1
HF_HUB_CACHE=<repo>/models/pyannote
```

и вызывает `Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")` —
модели резолвятся из этого каталога. После загрузки переменные восстанавливаются,
чтобы не ломать кэш Whisper (он живёт в дефолтном `~/.cache/huggingface/hub`).

## ⚠ Лицензия / распространение

Модели `speaker-diarization-3.1`, `segmentation-3.0`, `speaker-diarization-community-1`
— **gated** (модель pyannote, исследовательская лицензия, нераспространение).
Они лежат здесь **только для офлайн-разворачивания на собственных стендах** без
доступа в интернет. НЕ публиковать репо публично и не распространять веса вовне.
Для онлайн-машин проще использовать `HF_TOKEN` (лицензии уже приняты на аккаунте —
пере-принимать не нужно, 32 МБ скачиваются за секунды).

## Обновление моделей

```
HF_TOKEN=hf_… python -m meeting_intelligence  # (или вручную snapshot_download)
# затем скопировать ~/.cache/huggingface/hub/models--pyannote--* сюда
```
