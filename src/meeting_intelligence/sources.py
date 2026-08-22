from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("meeting")

class MeetingError(Exception):
    pass

def fail(message: str, code: int = 2) -> None:
    log.error(message)
    raise SystemExit(code)

def _is_url(value: str | Path) -> bool:
    parsed = urlparse(str(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

# Domains that MUST go through proxy (blocked in Russia without VPN)
_PROXY_DOMAINS = frozenset({
    "youtube.com", "www.youtube.com", "youtu.be",
    "m.youtube.com", "music.youtube.com",
})

# Domains that MUST go direct (Russian-hosted, break through proxy)
_DIRECT_DOMAINS = frozenset({
    "vkvideo.ru", "vk.com", "vk.ru",
    "rutube.ru", "www.rutube.ru",
})

def _yt_proxy_for_url(url: str) -> str:
    """Determine the --proxy argument for yt-dlp based on URL domain.

    YouTube → MEETING_YT_PROXY (SOCKS5 tunnel, default socks5://127.0.0.1:12334).
    VK / Rutube → empty (direct connection, bypasses system proxy).
    Unknown → no proxy (safe default — won't break Russian-hosted content).
    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if hostname in _PROXY_DOMAINS:
        proxy = os.getenv("MEETING_YT_PROXY", "socks5://127.0.0.1:12334")
        log.info("Platform: YouTube → proxy %s", proxy)
        return proxy

    if hostname in _DIRECT_DOMAINS:
        log.info("Platform: %s → direct (no proxy)", hostname)
        return ""

    # Unknown domain: direct by default (safe for Russian platforms)
    log.info("Platform: %s (unknown) → direct (no proxy)", hostname)
    return ""


def _resolve_source(url_or_path: str | Path) -> Path:
    if not _is_url(url_or_path):
        return Path(url_or_path)
    if find_spec("yt_dlp") is None:
        fail("URL support requires yt-dlp; install meeting-intelligence[url]")

    download_dir = Path(tempfile.mkdtemp(prefix="meeting-intelligence-"))
    output_template = download_dir / "audio.%(ext)s"
    proxy_arg = _yt_proxy_for_url(str(url_or_path))
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-x",
        "--audio-format",
        "wav",
        "--no-playlist",
        "--proxy", proxy_arg,
        "--output",
        str(output_template),
        str(url_or_path),
    ]
    log.info("Downloading audio from URL")
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=600, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise MeetingError("yt-dlp timed out while downloading audio") from exc
    if result.returncode != 0:
        raise MeetingError(f"yt-dlp failed: {result.stderr[-400:]}")

    audio = download_dir / "audio.wav"
    if not audio.is_file() or audio.stat().st_size == 0:
        raise MeetingError("yt-dlp did not produce a WAV audio file")
    return audio


# ── Telegram voice ingest (ADR-010) ────────────────────────────────────────

def _is_tg_source(source: str) -> bool:
    """True if source is a Telegram handle/link (tg:user or t.me/...)."""
    s = str(source)
    return s.startswith("tg:") or "t.me/" in s or "t.me" in s


# ── Telegram post media (ADR-011) ──────────────────────────────────────────

import re as _re

_TG_POST_RE = _re.compile(
    r"^(?:tg:|https?://t\.me/|t\.me/)(?P<channel>[A-Za-z0-9_]+)/(?P<post>\d+)$"
)


def _parse_tg_post(source: str):
    """'t.me/<ch>/<N>', 'https://t.me/<ch>/<N>' или 'tg:<ch>/<N>'
    → ('<ch>', N); иначе None. Приватные 't.me/c/<chat>/<post>' вне scope v1."""
    m = _TG_POST_RE.match(str(source).strip())
    if not m:
        return None
    return m.group("channel"), int(m.group("post"))


def _tg_session_candidates() -> list:
    """Кандидаты пути userbot-сессии: $HERMES_HOME, затем ~/.hermes."""
    hermes_home = os.environ.get("HERMES_HOME")
    cands = []
    if hermes_home:
        cands.append(Path(hermes_home) / "tg-userbot" / "session_fixed")
    cands.append(Path.home() / ".hermes" / "tg-userbot" / "session_fixed")
    return cands


def _tg_session_path() -> Path:
    """Первый существующий кандидат (Telethon хранит <name>.session);
    если ничего не найдено — первичный кандидат (для понятной ошибки)."""
    cands = _tg_session_candidates()
    for c in cands:
        if _tg_session_exists(c):
            return c
    return cands[0]


def _tg_session_exists(session: Path) -> bool:
    """Telethon хранит <name>.session — принимать и голый путь, и с суффиксом."""
    return session.exists() or Path(str(session) + ".session").exists()


def _tg_post_client(session: Path, proxy):
    """Build a telethon client for post resolution. Overridable in tests."""
    import socks
    from telethon import TelegramClient

    API_ID = 37136103
    API_HASH = "2a2d8d5ee29b99ca77f1fed10a454988"
    return TelegramClient(str(session), API_ID, API_HASH, proxy=proxy)


def resolve_tg_source(
    handle: str,
    since: str | None = None,
    limit: int = 3000,
    output_dir: Path | None = None,
) -> list:
    """Download voice messages from a Telegram dialog via the local userbot.

    Returns a list of ``TgVoiceRef`` (dataclass from ``meeting_intelligence.ingest``).
    Only ``Message.voice`` and round ``Video`` are fetched. For DMs the speaker
    label is taken from TG metadata (owner when ``msg.out``, else sender name) —
    this is more accurate than acoustic diarization (ADR-010 §2).

    Requires a valid userbot session; fails fast otherwise. telethon is
    imported lazily so it stays an optional dependency.
    """
    from datetime import datetime, timezone

    from meeting_intelligence.models import TgVoiceRef

    session = _tg_session_path()
    if not _tg_session_exists(session):
        fail(f"Telegram ingest requires a local userbot session: {session}")

    if find_spec("telethon") is None:
        fail("Telegram ingest requires telethon; install meeting-intelligence[tg]")

    import socks
    from telethon import TelegramClient

    API_ID = 37136103
    API_HASH = "2a2d8d5ee29b99ca77f1fed10a454988"
    proxy = (socks.SOCKS5, "127.0.0.1", 12334)

    out = Path(output_dir) if output_dir else Path.cwd()
    out.mkdir(parents=True, exist_ok=True)

    async def _run():
        client = TelegramClient(str(session), API_ID, API_HASH, proxy=proxy)
        await client.connect()
        if not await client.is_user_authorized():
            fail("Telegram userbot session is invalid (SESSION_INVALID)")
        me = await client.get_me()
        owner_name = getattr(me, "first_name", None) or getattr(me, "username", "owner")
        entity = await client.get_entity(handle)

        since_dt = None
        if since:
            since_dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        messages = [msg async for msg in client.iter_messages(entity, limit=limit)]
        refs = await extract_tg_voice_refs(messages, owner_name, out, since_dt)
        await client.disconnect()
        return refs

    import asyncio

    return asyncio.run(_run())


async def extract_tg_voice_refs(
    messages: list, owner_name: str, out: Path, since_dt=None
) -> list:
    """Pure-ish filtering + DM attribution for fetched TG messages.

    Separated from ``resolve_tg_source`` so it is unit-testable without a live
    userbot/telethon. Keeps only voice and round-video messages, derives the
    speaker label from TG metadata (owner when ``msg.out``, else sender name),
    downloads each to ``out`` and returns ``TgVoiceRef`` objects.
    """
    from meeting_intelligence.models import TgVoiceRef

    refs: list = []
    for msg in messages:
        doc = getattr(msg, "voice", None)
        video = getattr(msg, "video", None)
        if video is not None and getattr(video, "round_message", False):
            doc = video
        if doc is None:
            continue
        if since_dt is not None and msg.date < since_dt:
            continue
        sender = getattr(msg, "sender", None)
        sender_name = (
            getattr(sender, "first_name", None)
            or getattr(sender, "username", None)
            or "unknown"
        )
        # DM attribution: out=True → owner sent it, else the peer.
        speaker = owner_name if getattr(msg, "out", False) else sender_name
        dt = msg.date.strftime("%Y%m%d_%H%M%S")
        path = out / f"{msg.id}_{dt}.ogg"
        await _download_voice(msg, path)
        dur = 0
        for attr in getattr(doc, "attributes", []):
            if hasattr(attr, "duration"):
                dur = attr.duration
                break
        refs.append(
            TgVoiceRef(
                msg_id=msg.id,
                date=msg.date,
                sender_label=speaker,
                is_out=bool(getattr(msg, "out", False)),
                ogg_path=path,
                duration_sec=dur,
            )
        )
    return refs


async def _download_voice(msg, path: Path) -> None:
    """Download a voice message to ``path``. Overridable in tests."""
    import telethon  # noqa: F401 (ensures dependency at call time)

    client = getattr(msg, "_client", None)
    if client is not None:
        await client.download_media(msg, file=str(path))
    else:
        # Test path: write a placeholder so the ref has a real file.
        Path(path).write_bytes(b"fake-ogg")


def _copy_session_for_read(session: Path) -> Path:
    """Копия .session во временную папку — живой юзербот держит SQLite-lock,
    второй клиент по оригиналу падает с 'database is locked'. Ключ авторизации
    статичен, копии достаточно для скачивания; копия удаляется после."""
    import shutil
    import tempfile

    src = session if session.exists() else Path(str(session) + ".session")
    tmpdir = Path(tempfile.mkdtemp(prefix="meeting-tg-sess-"))
    dst = tmpdir / "session_copy"
    shutil.copy2(src, Path(str(dst) + ".session"))
    return dst


def resolve_tg_post_media(
    channel: str,
    post_id: int,
    output_dir: Path | None = None,
) -> Path:
    """Download the media attachment of one Telegram post (ADR-011).

    ``t.me/<channel>/<post_id>`` → локальный файл (видео/документ/голос).
    Дальше файл идёт обычным конвейером (лимиты → ffmpeg → whisper).
    Приватные чаты ('t.me/c/<chat>/<post>') вне scope v1.
    """
    import shutil
    import socks

    session = _tg_session_path()
    if not _tg_session_exists(session):
        fail(f"Telegram ingest requires a local userbot session: {session}")

    if find_spec("telethon") is None:
        fail("Telegram ingest requires telethon; install meeting-intelligence[tg]")

    out = Path(output_dir) if output_dir else Path.cwd()
    out.mkdir(parents=True, exist_ok=True)
    proxy = (socks.SOCKS5, "127.0.0.1", 12334)

    async def _run() -> Path:
        session_copy = _copy_session_for_read(session)
        try:
            client = _tg_post_client(session_copy, proxy)
            await client.connect()
            if not await client.is_user_authorized():
                fail("Telegram userbot session is invalid (SESSION_INVALID)")
            entity = await client.get_entity(channel)
            msg = await client.get_messages(entity, ids=int(post_id))
            if msg is None or getattr(msg, "media", None) is None:
                fail(f"Message {post_id} in {channel} has no downloadable media")
            video = getattr(msg, "video", None)
            document = getattr(msg, "document", None)
            voice = getattr(msg, "voice", None)
            photo = getattr(msg, "photo", None)
            if video is None and document is None and voice is None and photo is None:
                fail(
                    f"Message {post_id} in {channel}: media type not supported "
                    "(only video/document/voice/photo; other types are out of scope)"
                )
            caption = getattr(msg, "message", "") or ""
            is_photo = (
                photo is not None
                and video is None
                and document is None
                and voice is None
            )
            if is_photo:
                # ADR-012: фото → vision-конвейер; текст появится позже,
                # здесь только скачиваем картинку и сохраняем подпись.
                target = out / f"{channel}_{post_id}.jpg"
                path = await client.download_media(msg, file=str(target))
                Path(str(path)).with_suffix(".caption.txt").write_text(
                    caption, encoding="utf-8"
                )
            else:
                target = out / f"{channel}_{post_id}.mp4"
                path = await client.download_media(msg, file=str(target))
            await client.disconnect()
        finally:
            shutil.rmtree(session_copy.parent, ignore_errors=True)
        return Path(path)

    import asyncio

    return asyncio.run(_run())
