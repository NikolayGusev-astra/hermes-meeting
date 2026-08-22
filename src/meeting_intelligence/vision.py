"""Image → text bridge (ADR-012).

Правило роутинга из статьи «Vision в API за копейки»: локальные модели вместо
нативного зрения. Два режима:

- ``vl``  (дефолт) — LFM2.5-VL в LM Studio: фото, интерфейсы, схемы;
- ``ocr`` — OvisOCR2 на отдельном llama.cpp (:8017): документы, сканы.

Выбор режима: аргумент ``mode``, env ``MEETING_VISION_MODE``, дефолт ``vl``.
Бэкенды: ``MEETING_LLM_BASE_URL`` (LM Studio) и ``MEETING_OCR_BASE_URL``
(порт из статьи). Никаких новых зависимостей — urllib.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from .sources import MeetingError

log = logging.getLogger("meeting")

OCR_PROMPT = (
    "Extract all readable content from the image in natural human "
    "reading order and output the result as a single Markdown "
    "document. Format formulas as LaTeX. Format tables as HTML. "
    "Preserve the original text without translation."
)
VL_PROMPT = (
    "Опиши изображение как раздел документации: что изображено, ключевые "
    "зоны/объекты, весь видимый текст дословно. Только то, что видно."
)


def _b64_data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def _backend_url(mode: str) -> str:
    if mode == "ocr":
        base = os.getenv("MEETING_OCR_BASE_URL", "http://127.0.0.1:8017/v1")
    else:
        # Выделенный llama.cpp (:8018) приоритетнее общего LM Studio —
        # vision не зависит от того, какая модель загружена в GUI.
        base = os.getenv(
            "MEETING_VISION_BASE_URL",
            os.getenv("MEETING_LLM_BASE_URL", "http://localhost:1234/v1"),
        )
    return base.rstrip("/") + "/chat/completions"


def _model_name(mode: str) -> str:
    if mode == "ocr":
        return os.getenv("MEETING_OCR_MODEL", "ovisocr2")
    return os.getenv("MEETING_VISION_MODEL", "lfm2.5-vl-3b")


def describe_image(path: Path, mode: str | None = None) -> str:
    """Отправить картинку в локальный vision-бэкенд, вернуть текст.

    Режим: 'vl' (описание) | 'ocr' (документы); по умолчанию env
    MEETING_VISION_MODE или 'vl'.
    """
    image = Path(path)
    if not image.is_file() or image.stat().st_size == 0:
        raise MeetingError(f"Vision input missing or empty: {image}")

    mode = (mode or os.getenv("MEETING_VISION_MODE", "vl")).lower()
    payload = {
        "model": _model_name(mode),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _b64_data_url(image)}},
                    {"type": "text", "text": OCR_PROMPT if mode == "ocr" else VL_PROMPT},
                ],
            }
        ],
        "max_tokens": 4096,
        "temperature": 0,
    }
    req = urllib.request.Request(
        _backend_url(mode),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    log.info("Vision (%s): %s -> %s", mode, image.name, req.full_url)
    try:
        with urlopen(req, timeout=300) as resp:  # noqa: S310 (local backends only)
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode(errors="replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        raise MeetingError(
            f"Vision backend returned HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise MeetingError(
            f"Vision backend unreachable at {req.full_url} "
            f"(mode={mode}) — запущен ли LM Studio / llama-server? ({exc.reason})"
        ) from exc
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise MeetingError(f"Unexpected vision backend response: {data!r:.200}") from exc


urlopen = urllib.request.urlopen
