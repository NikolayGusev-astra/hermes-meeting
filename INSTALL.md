# Установка «Встречи» (чистая машина)

Дашборд встреч для Hermes Desktop: список обработанных транскрипций и
артефактов (протокол, саммари, аналитическая записка, реестр решений,
поручения), поиск/фильтр по типу и имени, раскрытие карточки и
открытие/скачивание файлов.

## Порядок установки

### 1. Установить плагин

```bash
hermes plugins install git@gitflic.ru:manve-sulimo2/hermes-meeting.git
```

Клонирует репо в `~/.hermes/plugins/meeting-intelligence/`. На вопрос
`Enable now? [y/N]` ответьте `y` (или включите позже — шаг 3).

### 2. Зависимости и виджет

```bash
bash ~/.hermes/plugins/meeting-intelligence/scripts/install.sh
```

- `pip install -r requirements.txt` в venv Hermes — для бэкенда дашборда
  нужен только `fastapi` (+ `pydantic`/`uvicorn`). **Без `fastapi` бэкенд
  `dashboard/plugin_api.py` не смонтируется.**
- копирование `com.hermes.desktop/plugin.js` →
  `desktop-plugins/meeting-intelligence/plugin.js` (виджет вкладки).

> Полный пайплайн транскрипции (Whisper) тянет тяжёлые зависимости (torch и
> др.) и **опционален** — нужен только если вы запускаете обработку аудио
> через инструменты плагина. Дашборд работает и без них. Тяжёлые deps
> ставятся отдельно: `pip install -e .[all]` (варианты: `[gpu]`, `[cloud]`,
> `[diarization]`).

### 3. Включить (если не ответили `y` на шаге 1)

```yaml
plugins:
  enabled:
    - meeting-intelligence
```

### 4. Перезапустить gateway

Закрыть и открыть Hermes Desktop (или `hermes gateway restart`). После рестарта
монтируется `/api/plugins/meeting-intelligence/*` — включая
`/meetings/{name}/file/{filename}` (открытие/скачивание артефактов) — и в
сайдбаре появится вкладка **«Встречи»** (🎤). Если не появилась —
`Ctrl/Cmd+K → Reload desktop plugins`.

> Маршрут открытия файлов (`/file/...`) становится доступен только после
> рестарта gateway. До рестарта просмотр/поиск/раскрытие работают, но клик по
> файлу вернёт 404.

## Папка встреч

По умолчанию корень = `MEETING_ROOT=C:\Work\Assist\meeting` (переопределить
через переменную окружения `MEETING_ROOT`). Каждая встреча — подкаталог вида
`{дата}_{тип}_{тема}` (например `2026-08-12_встреча_ИИ-стратегия`) с
артефактами `.docx` / `.xlsx` / `.txt`. Тип (встреча/лекция/интервью/…)
определяется из имени папки и используется для фильтра и бейджа.

## Проверка

```bash
# 401 = маршрут есть (нужен токен сессии); 404 = не смонтирован.
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:<port>/api/plugins/meeting-intelligence/meetings
```

## Обновление

```bash
hermes plugins update meeting-intelligence
bash ~/.hermes/plugins/meeting-intelligence/scripts/deploy-desktop-plugin.sh
```
