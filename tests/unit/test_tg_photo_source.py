"""Offline tests: photo posts route through the vision bridge (ADR-012)."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from meeting_intelligence import sources  # noqa: E402


class _FakeClient:
    def __init__(self, msg):
        self._msg = msg

    async def connect(self):
        pass

    async def is_user_authorized(self):
        return True

    async def disconnect(self):
        pass

    async def get_entity(self, handle):
        return types.SimpleNamespace(username=handle)

    async def get_messages(self, entity, ids=None):
        return self._msg

    async def download_media(self, msg, file=None, thumb=None):
        Path(file).write_bytes(b"fakejpeg")
        return file


def _photo_msg(caption=""):
    photo = types.SimpleNamespace(round_message=False)
    return types.SimpleNamespace(
        id=42,
        video=None,
        document=None,
        voice=None,
        photo=photo,
        media=object(),
        message=caption,
    )


def test_resolve_tg_post_photo_downloads_image(monkeypatch, tmp_path):
    (tmp_path / "session_fixed").parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        sources, "_tg_session_path",
        lambda: tmp_path / "tg-userbot" / "session_fixed",
    )
    (tmp_path / "tg-userbot").mkdir()
    (tmp_path / "tg-userbot" / "session_fixed.session").write_bytes(b"s")
    monkeypatch.setattr(
        sources, "_tg_post_client", lambda s, p: _FakeClient(_photo_msg("подпись"))
    )

    got = sources.resolve_tg_post_media("neuraldeep", 42, output_dir=tmp_path / "out")
    assert got.exists()
    assert got.suffix == ".jpg"
    # подпись сохранена рядом для транскрипта
    cap = got.with_suffix(".caption.txt")
    assert cap.exists() and "подпись" in cap.read_text(encoding="utf-8")


def test_photo_beats_nothing_video_wins_over_photo(monkeypatch, tmp_path):
    """Смешанный пост: видео побеждает фото."""
    (tmp_path / "tg-userbot").mkdir(parents=True)
    (tmp_path / "tg-userbot" / "session_fixed.session").write_bytes(b"s")
    msg = _photo_msg()
    msg.video = types.SimpleNamespace(round_message=False)
    monkeypatch.setattr(
        sources, "_tg_session_path",
        lambda: tmp_path / "tg-userbot" / "session_fixed",
    )
    downloaded = []

    class _C(_FakeClient):
        async def download_media(self, msg, file=None, thumb=None):
            downloaded.append(Path(file).suffix)
            Path(file).write_bytes(b"x")
            return file

    monkeypatch.setattr(sources, "_tg_post_client", lambda s, p: _C(msg))
    got = sources.resolve_tg_post_media("ch", 7, output_dir=tmp_path / "o")
    assert downloaded == [".mp4"]
    assert got.suffix == ".mp4"


def test_pipeline_transcribes_photo_via_vision(monkeypatch, tmp_path):
    """transcribe() с фото-постом: vision-описание становится транскриптом."""
    import meeting_intelligence.pipeline as pipeline

    fake_img = tmp_path / "neuraldeep_42.jpg"
    fake_img.write_bytes(b"jpg")

    monkeypatch.setattr(
        pipeline, "resolve_tg_post_media",
        lambda ch, pid, output_dir=None: fake_img,
    )
    called = {}

    def fake_describe(path, mode=None):
        called["img"] = Path(path)
        return "Описание фото"

    monkeypatch.setattr(pipeline, "describe_image", fake_describe)
    params = pipeline.TranscribeParams(
        source="https://t.me/neuraldeep/42", output=tmp_path / "p.txt"
    )
    res = pipeline.transcribe(params)
    assert res.transcript_path == tmp_path / "p.txt"
    assert "Описание фото" in res.transcript
