"""Offline tests for Telegram post media source (ADR-011).

`t.me/<channel>/<post_id>` (или `tg:<channel>/<post_id>`) → резолв одного
сообщения через userbot, скачивание медиа-вложения, дальше обычный конвейер.
Инжест диалога (ADR-010) не должен измениться.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from meeting_intelligence import sources  # noqa: E402


# ── Parser matrix ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://t.me/neuraldeep/2288", ("neuraldeep", 2288)),
        ("http://t.me/neuraldeep/2288", ("neuraldeep", 2288)),
        ("t.me/neuraldeep/2288", ("neuraldeep", 2288)),
        ("tg:neuraldeep/2288", ("neuraldeep", 2288)),
        ("tg:neuraldeep/1", ("neuraldeep", 1)),
    ],
)
def test_parse_tg_post_matches(raw, expected):
    assert sources._parse_tg_post(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "tg:neuraldeep",
        "t.me/neuraldeep",
        "https://t.me/neuraldeep",
        "tg:neuraldeep/abc",  # нечисловой пост
        "https://youtube.com/live/x0j1kcagoXg",
        "C:/Work/audio.wav",
    ],
)
def test_parse_tg_post_rejects(raw):
    assert sources._parse_tg_post(raw) is None


def test_dialog_source_is_not_post():
    """ADR-010 behavior guard: dialog handles stay dialogs."""
    assert sources._parse_tg_post("tg:Evgenius_Morozov") is None
    assert sources._is_tg_source("tg:Evgenius_Morozov") is True
    # Пост — тоже tg-источник (для CLI-подсказок), но парсится в (channel, id)
    assert sources._is_tg_source("https://t.me/neuraldeep/2288") is True


# ── resolve_tg_post_media (mocked telethon, no network) ───────────────────


class _FakeClient:
    def __init__(self, msg):
        self._msg = msg
        self.downloaded_to = None

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

    async def download_media(self, msg, file=None):
        self.downloaded_to = file
        Path(file).write_bytes(b"fake-mp4")
        return file


def _patch_session(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sources, "_tg_session_path", lambda: tmp_path / "session_fixed"
    )
    (tmp_path / "session_fixed").write_bytes(b"session")


def test_resolve_tg_post_media_downloads(monkeypatch, tmp_path):
    _patch_session(monkeypatch, tmp_path)
    msg = types.SimpleNamespace(
        id=2288,
        video=types.SimpleNamespace(round_message=False),
        document=None,
        voice=None,
        media=object(),
    )
    client = _FakeClient(msg)
    monkeypatch.setattr(
        sources, "_tg_post_client", lambda session, proxy: client
    )

    out_dir = tmp_path / "out"
    got = sources.resolve_tg_post_media("neuraldeep", 2288, output_dir=out_dir)
    assert got.exists()
    assert got.stat().st_size > 0
    assert got.name == "neuraldeep_2288.mp4"


def test_resolve_tg_post_no_media_fails(monkeypatch, tmp_path):
    _patch_session(monkeypatch, tmp_path)
    msg = types.SimpleNamespace(
        id=1, video=None, document=None, voice=None, media=None
    )
    monkeypatch.setattr(
        sources, "_tg_post_client", lambda session, proxy: _FakeClient(msg)
    )
    with pytest.raises(SystemExit):
        sources.resolve_tg_post_media("neuraldeep", 1, output_dir=tmp_path / "o2")


def test_resolve_tg_post_no_downloadable_fails(monkeypatch, tmp_path):
    """media есть, но ни video/document/voice — тоже fail (фото, например)."""
    _patch_session(monkeypatch, tmp_path)
    msg = types.SimpleNamespace(
        id=2,
        video=None,
        document=None,
        voice=None,
        media=object(),
    )
    monkeypatch.setattr(
        sources, "_tg_post_client", lambda session, proxy: _FakeClient(msg)
    )
    with pytest.raises(SystemExit):
        sources.resolve_tg_post_media("neuraldeep", 2, output_dir=tmp_path / "o3")


# ── Pipeline routing ──────────────────────────────────────────────────────


def test_pipeline_routes_tg_post_to_local_file(monkeypatch, tmp_path):
    """transcribe() с постом должен пойти в файловую ветку, не в ingest_telegram."""
    import meeting_intelligence.pipeline as pipeline

    fake_media = tmp_path / "neuraldeep_2288.mp4"
    fake_media.write_bytes(b"fake")

    called = {}
    monkeypatch.setattr(
        pipeline,
        "resolve_tg_post_media",
        lambda ch, pid, output_dir=None: called.update(
            channel=ch, post=pid
        )
        or fake_media,
    )
    monkeypatch.setattr(
        pipeline,
        "check_resource_limits",
        lambda p, **k: called.setdefault("limits", True),
    )
    monkeypatch.setattr(
        pipeline,
        "extract_audio",
        lambda src, dst: called.setdefault("extracted", (src, dst)) or dst,
    )
    monkeypatch.setattr(
        pipeline,
        "transcribe_audio",
        lambda *a, **k: ("[00:00->00:01] SPEAKER_00 | hi", {"diarization": "none"}),
    )

    params = pipeline.TranscribeParams(
        source="https://t.me/neuraldeep/2288",
        output=tmp_path / "t.txt",
    )
    res = pipeline.transcribe(params)
    assert called.get("channel") == "neuraldeep"
    assert called.get("post") == 2288
    assert called.get("extracted") is not None
    assert res.transcript_path == tmp_path / "t.txt"


def test_pipeline_dialog_still_ingests(monkeypatch, tmp_path):
    """ADR-010 guard: диалоговый источник по-прежнему уходит в ingest_telegram."""
    import meeting_intelligence.pipeline as pipeline

    called = {}

    def fake_ingest(handle, **kw):
        called["handle"] = handle
        return []

    monkeypatch.setattr(
        "meeting_intelligence.ingest.ingest_telegram",
        fake_ingest,
    )
    monkeypatch.setattr(
        pipeline, "resolve_tg_post_media",
        lambda *a, **k: pytest.fail("post resolver must not run for dialogs"),
    )

    params = pipeline.TranscribeParams(
        source="tg:Evgenius_Morozov", output=tmp_path / "x.txt"
    )
    res = pipeline.transcribe(params)
    assert called.get("handle") == "Evgenius_Morozov"
    assert res.transcript_path == Path("nul")
