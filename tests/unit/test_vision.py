"""Offline tests for the image→text bridge (ADR-012).

Фото-пост из Telegram → VL-описание (LM Studio) или OCR (llama.cpp/OvisOCR2)
→ текст вместо транскрипта. Никаких сетевых вызовов — urllib мокается.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from meeting_intelligence import vision  # noqa: E402
from meeting_intelligence.sources import MeetingError  # noqa: E402


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def test_describe_image_posts_b64_and_returns_content(monkeypatch, tmp_path):
    img = tmp_path / "post.jpg"
    img.write_bytes(b"\xff\xd8fakejpeg")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        body = json.loads(req.data.decode())
        captured["body"] = body
        content = base64.b64decode(
            body["messages"][0]["content"][0]["image_url"]["url"].split(",", 1)[1]
        )
        captured["img_bytes"] = content
        return _FakeResponse(
            {"choices": [{"message": {"content": "На фото: таблица."}}]}
        )

    monkeypatch.setattr(vision, "urlopen", fake_urlopen)
    out = vision.describe_image(img)
    assert out == "На фото: таблица."
    assert captured["img_bytes"] == b"\xff\xd8fakejpeg"
    assert captured["url"].endswith("/chat/completions")
    assert captured["body"]["max_tokens"] == 4096
    assert captured["body"]["temperature"] == 0


def test_describe_image_ocr_mode_uses_ocr_backend(monkeypatch, tmp_path):
    img = tmp_path / "scan.png"
    img.write_bytes(b"png")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return _FakeResponse({"choices": [{"message": {"content": "# Doc"}}]})

    monkeypatch.setattr(vision, "urlopen", fake_urlopen)
    out = vision.describe_image(img, mode="ocr")
    assert out == "# Doc"
    assert "127.0.0.1:8017" in captured["url"]
    assert "Markdown" in captured["body"]["messages"][0]["content"][1]["text"]


def test_vl_mode_prefers_dedicated_url(monkeypatch, tmp_path):
    """MEETING_VISION_BASE_URL отвязывает vl от общего LM Studio адреса."""
    img = tmp_path / "x.jpg"
    img.write_bytes(b"x")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setenv("MEETING_VISION_BASE_URL", "http://127.0.0.1:8018/v1")
    monkeypatch.delenv("MEETING_LLM_BASE_URL", raising=False)
    monkeypatch.setattr(vision, "urlopen", fake_urlopen)
    vision.describe_image(img)
    assert "127.0.0.1:8018" in captured["url"]


def test_vl_mode_falls_back_to_llm_base_url(monkeypatch, tmp_path):
    """Без выделенного адреса — старое поведение (LM Studio)."""
    img = tmp_path / "x.jpg"
    img.write_bytes(b"x")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.delenv("MEETING_VISION_BASE_URL", raising=False)
    monkeypatch.setattr(vision, "urlopen", fake_urlopen)
    vision.describe_image(img)
    assert "localhost:1234" in captured["url"]


def test_describe_image_unreachable_fails_with_hint(monkeypatch, tmp_path):
    import urllib.error

    img = tmp_path / "x.jpg"
    img.write_bytes(b"x")

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(vision, "urlopen", fake_urlopen)
    with pytest.raises(MeetingError, match="Vision backend unreachable"):
        vision.describe_image(img)


def test_describe_image_http_error_surfaces_body(monkeypatch, tmp_path):
    import urllib.error

    img = tmp_path / "x.jpg"
    img.write_bytes(b"x")

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 500, "boom", hdrs=None, fp=None
        )

    monkeypatch.setattr(vision, "urlopen", fake_urlopen)
    with pytest.raises(MeetingError, match="500"):
        vision.describe_image(img)
