# Диагностика проблем / Troubleshooting

## Brotli DecodingError при загрузке моделей HuggingFace

**Симптом:** `httpx.DecodingError: brotli: decoder process called with data when 'can_accept_more_data()' is False`

**Причина:** Конфликт `brotlicffi` (CFFI-обёртка) и `brotli` (C-реализация) в Python-окружении. `httpx` и `urllib3` цепляются за битую версию brotli.

**Решение (одно из):**

1. Быстрое — отключить сжатие:
   ```bash
   export HF_HUB_DISABLE_COMPRESSION=1
   ```

2. Правильное — переустановить brotlicffi:
   ```bash
   pip install --force-reinstall brotlicffi
   # или в конкретном venv:
   path/to/venv/Scripts/python.exe -m pip install --force-reinstall brotlicffi
   ```

3. Альтернатива — использовать C-версию brotli:
   ```bash
   pip uninstall brotlicffi -y
   pip install brotli
   ```

**Проверка:**
```bash
python -c "import urllib3; print('OK')"
```

---

## CUDA-модель падает в CPU

**Симптом:** `CUDA GPU found but runtime missing. Install: pip install meeting-intelligence[gpu]`

**Причина:** В текущем venv нет `nvidia-cublas-cu12`.

**Решение:**
```bash
pip install nvidia-cublas-cu12
# CUDA DLL будет в site-packages/nvidia/cublas/bin/

# Проверить:
python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```

**Важно:** Модели в HuggingFace-кеше (`~/.cache/huggingface/hub/`) общие для ВСЕХ Python-окружений. Скачали один раз — используете везде. Транскрибируйте ТЕМ Python, где есть CUDA.

---

## Прокси: HuggingFace vs LLM

| Направление | Прокси | Почему |
|-------------|--------|--------|
| HuggingFace (модели) | Без прокси (`http_proxy=''`) | CDN HuggingFace доступен напрямую через VPN. SOCKS5 рвёт большие файлы. |
| LLM localhost | `no_proxy='*'` | LM Studio/Ollama на localhost не должны идти через прокси |
| yt-dlp (YouTube) | SOCKS5 `socks5://127.0.0.1:12334` | YouTube заблокирован, только через тоннель |

---

## distil-large-v3.5 не скачивается через прокси

**Проблема:** SOCKS5-прокси (Xray) рвёт HTTP-соединения с HuggingFace на больших файлах (>500 MB). Мелкие файлы (tokenizer, config) скачиваются, бинарные веса — нет.

**Решение:** Скачивать без прокси. HuggingFace CDN доступен напрямую через VPN-тоннель.

```bash
http_proxy='' https_proxy='' HF_HUB_DISABLE_COMPRESSION=1 python -m meeting_intelligence transcribe video.mp4 --model distil-large-v3.5 --language ru
```

---

## Язык авто-детекта ошибается (русский → en)

**Симптом:** Whisper определяет русскую речь как `language=en`, выдаёт транслитерацию вместо кириллицы.

**Решение:** Явно указывать язык флагом `--language ru`.

В будущем: плагин проверяет плотность русских паттернов (Минюст, Росстандарт, отчества) и предупреждает, если `en`-транскрипт выглядит как русский.

---

## Symlinks warning на Windows при загрузке моделей

**Симптом:** `huggingface_hub` cache-system uses symlinks by default but your machine does not support them...

**Решение:** Windows не поддерживает symlinks без Developer Mode. На функциональность не влияет — модели работают, просто занимают больше места. Warning подавляется:

```bash
export HF_HUB_DISABLE_SYMLINKS_WARNING=1
# или в коде:
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
```

```bash
# CUDA работает?
python -c "from ctranslate2 import get_cuda_device_count; print(get_cuda_device_count())"

# Модель скачана?
ls ~/.cache/huggingface/hub/models--Systran--faster-whisper-medium

# urllib3 не сломан?
python -c "import urllib3; print('OK')"

# Версия плагина
meeting --version
```
