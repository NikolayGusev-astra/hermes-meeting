# install.md — agent runbook (Установка «Встречи», чистая машина)

Пошаговый runbook для ИИ-агента или человека: выполняй пункты подряд. Каждый шаг
сопровождается командой и проверкой успеха. `hermes plugins install` НЕ делает всё
сам — pip и виджет ставит пост-скрипт `scripts/install.sh` (by design, изоляция).

> «Встречи» = дашборд обработанных транскрипций и артефактов (протокол, саммари,
> аналитика, реестр решений, поручения): поиск/фильтр, раскрытие карточек,
> открытие/скачивание файлов. Бекенд — FastAPI-роутер в gateway (только чтение);
> фронтенд — React-виджет в сайдбаре Hermes Desktop.

**HERMES_HOME по ОС** (критично на macOS — промах = невидимая вкладка):

| ОС | HERMES_HOME | каталог клона |
|----|-------------|---------------|
| macOS | `~/Library/Application Support/hermes` | `…/plugins/meeting-intelligence` |
| Windows | `%LOCALAPPDATA%\hermes` | `…/plugins/meeting-intelligence` |
| Linux | `~/.hermes` | `…/plugins/meeting-intelligence` |

> ⚠ **Зависимости**: для работы **дашборда** бекенду нужен только `fastapi`
> (+ `pydantic`/`uvicorn`) — они уже есть в gateway, отдельно ставить не надо.
> Полный пайплайн транскрипции (Whisper) тянет тяжёлые deps (torch и др.) и
> **опционален** — нужен лишь для обработки аудио. `install.sh` ставит
> `requirements.txt`; если нужен только дашборд — pip можно пропустить.

---

## 0. Предусловия

- **Hermes Desktop** установлен и запущен хотя бы раз (создаёт HERMES_HOME).
- **git** и **bash** (Windows — Git Bash).
- (Опционально) **MEETING_ROOT** — папка с встречами; по умолчанию
  `C:\Work\Assist\meeting` (переопределить env). Каждая встреча — подкаталог
  `{дата}_{тип}_{тема}` с артефактами `.docx`/`.xlsx`/`.txt`.

## 1. Установить плагин

```bash
hermes plugins install git@gitflic.ru:manve-sulimo2/hermes-meeting.git
```
На запрос `Enable now? [y/N]` ответь **`y`**.
✓ Успех: `✓ Plugin meeting-intelligence enabled.` + `gateway restart`. Клон в `$HERMES_HOME/plugins/meeting-intelligence/`.

> Установщик напечатает «declares Python dependencies (not installed automatically)»
> и, возможно, варнинг «ignored unknown top-level field: python_dependencies» —
> нормально (поле знает код печати, но validate-список текущей версии Hermes его не
> включает). Pip — на шаге 2.

## 2. Пост-установка: pip + виджет (одной командой)

```bash
# Linux/Windows:
bash ~/.hermes/plugins/meeting-intelligence/scripts/install.sh
# macOS:
bash "$HOME/Library/Application Support/hermes/plugins/meeting-intelligence/scripts/install.sh"
```
Скрипт ставит `requirements.txt` в venv Hermes и вызывает `deploy-desktop-plugin.sh`
(копирует `com.hermes.desktop/plugin.js` в `$HERMES_HOME/desktop-plugins/meeting-intelligence/`).
✓ Успех: `✓ deployed` + блок «далее вручную».

Только виджет (без pip, если нужен только дашборд):
```bash
bash ~/.hermes/plugins/meeting-intelligence/scripts/deploy-desktop-plugin.sh
```

## 3. Включить бекенд (если не ответил `y` на шаге 1)

```bash
hermes plugins enable meeting-intelligence
```
Либо вручную — `meeting-intelligence` в `plugins.enabled` в `$HERMES_HOME/config.yaml`:
```yaml
plugins:
  enabled:
    - meeting-intelligence
```
Без этого `dashboard/plugin_api.py` НЕ монтируется gateway.

## 4. Перезапустить gateway + Desktop

```bash
hermes gateway restart
```
Затем **полный** рестарт Hermes Desktop:
- **macOS**: `⌘Q` (полный выход), не просто закрыть окно.
- **Windows/Linux**: закрыть и открыть приложение.

> «Reload desktop plugins» (`Ctrl/Cmd+K`) НЕ подхватывает НОВЫЕ плагины — нужен
> полный рестарт. Маршрут `/meetings/{name}/file/{filename}` (открытие/скачивание
> артефактов) становится доступен тоже только после рестарта gateway (до рестарта
> просмотр/поиск работают, но клик по файлу → 404).

---

## Проверка (что значит «готово»)

1. В сайдбаре есть вкладка **«Встречи»** (🎤) → открывается без «Ошибка загрузки».
2. Бекенд отвечает:
   ```bash
   HH=~/.hermes   # macOS: HH="$HOME/Library/Application Support/hermes"
   # порт gateway (или прокси); 401 = маршрут есть (нужен токен), 404 = не смонтирован
   curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:<port>/api/plugins/meeting-intelligence/meetings
   ```

## Частые проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| Вкладки нет (macOS) | виджет не в тот home | шаг 2 с путём `~/Library/Application Support/hermes/...` |
| Вкладка есть, «Ошибка загрузки» | бекенд не смонтирован | шаг 3 (enable) + шаг 4 (restart) |
| Клик по файлу → 404 | gateway не перезапущен | шаг 4 (полный рестарт) |
| `python` not found (macOS) | есть только `python3` | venv Hermes: `$HH/hermes-agent/venv/bin/python` |
| CRLF: `/bin/bash^M: bad interpreter` | скрипт скачан не через git | `dos2unix ~/.hermes/plugins/meeting-intelligence/scripts/*.sh` |
| Папка встреч пуста | `MEETING_ROOT` указывает не туда | задать env `MEETING_ROOT` и перезапустить gateway |

## Обновление

```bash
hermes plugins update meeting-intelligence
bash ~/.hermes/plugins/meeting-intelligence/scripts/install.sh   # если менялись pip/виджет
hermes gateway restart
# + полный рестарт Desktop, если менялся plugin.js (виджет)
```
