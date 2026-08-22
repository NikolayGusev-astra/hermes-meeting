"""Album (media group) support for t.me post links.

A t.me/<channel>/<id> link may point at any element of an album
(media group). The plugin must resolve the whole group via grouped_id
and return every media file (videos, photos). The pipeline then builds
a composite transcript: caption + video transcripts + photo descriptions.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from meeting_intelligence import sources  # noqa: E402


class _FakeClient:
    """Fake telethon client serving a fixed media group."""

    def __init__(self, group: dict):
        self._group = group  # msg_id -> message
        self.downloaded = []

    async def connect(self):
        pass

    async def is_user_authorized(self):
        return True

    async def disconnect(self):
        pass

    async def get_entity(self, handle):
        return types.SimpleNamespace(username=handle)

    async def get_messages(self, entity, ids=None):
        return self._group[ids]

    async def iter_messages(self, entity, ids=None, limit=None):
        """grouped_id lookup: Telethon API returns siblings for the anchor id."""
        anchor = self._group[ids]
        for msg in self._group.values():
            if msg.grouped_id and msg.grouped_id == anchor.grouped_id:
                yield msg

    async def download_media(self, msg, file=None):
        self.downloaded.append(msg.id)
        p = Path(file)
        p.write_bytes(b"media-" + str(msg.id).encode())
        return p


def _msg(mid: int, grouped_id=None, video=False, photo=False):
    return types.SimpleNamespace(
        id=mid,
        grouped_id=grouped_id,
        video=types.SimpleNamespace(round_message=False) if video else None,
        document=None,
        voice=None,
        photo=types.SimpleNamespace() if photo else None,
        media=object() if (video or photo) else None,
    )


def _patch(monkeypatch, tmp_path, client):
    monkeypatch.setattr(
        sources, "_tg_session_path", lambda: tmp_path / "s"
    )
    (tmp_path / "s.session").write_bytes(b"sess")
    monkeypatch.setattr(
        sources, "_tg_post_client", lambda session, proxy: client
    )
    monkeypatch.setattr(
        sources, "_copy_session_for_read", lambda s: s
    )


def test_resolve_tg_post_album_returns_all_media(monkeypatch, tmp_path):
    """Link to the first album item must fetch every video AND photo."""
    gid = 111
    group = {
        100: _msg(100, video=True),
        101: _msg(101, photo=True),
        102: _msg(102, photo=True),
    }
    for m in group.values():
        m.grouped_id = gid
    client = _FakeClient(group)
    _patch(monkeypatch, tmp_path, client)

    got = sources.resolve_tg_post_media("chan", 100, output_dir=tmp_path / "o")
    names = sorted(p.name for p in got)
    assert names == [
        "chan_100.mp4",  # видео
        "chan_101.jpg",  # фото
        "chan_102.jpg",
    ]
    assert client.downloaded == [100, 101, 102]


def test_resolve_tg_post_single_video_unchanged(monkeypatch, tmp_path):
    """Non-album post keeps the single-file behavior."""
    client = _FakeClient({2288: _msg(2288, video=True)})
    _patch(monkeypatch, tmp_path, client)

    got = sources.resolve_tg_post_media("neuraldeep", 2288, output_dir=tmp_path / "o")
    assert len(got) == 1
    assert got[0].name == "neuraldeep_2288.mp4"


def test_resolve_tg_post_album_photo_only(monkeypatch, tmp_path):
    """Photo-only album still resolves (vision bridge handles them downstream)."""
    gid = 222
    group = {200: _msg(200, photo=True), 201: _msg(201, photo=True)}
    for m in group.values():
        m.grouped_id = gid
    client = _FakeClient(group)
    _patch(monkeypatch, tmp_path, client)

    got = sources.resolve_tg_post_media("chan", 200, output_dir=tmp_path / "o")
    assert [p.name for p in got] == ["chan_200.jpg", "chan_201.jpg"]
