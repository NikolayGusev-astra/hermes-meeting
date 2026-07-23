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

def _resolve_source(url_or_path: str | Path) -> Path:
    if not _is_url(url_or_path):
        return Path(url_or_path)
    if find_spec("yt_dlp") is None:
        fail("URL support requires yt-dlp; install meeting-intelligence[url]")

    download_dir = Path(tempfile.mkdtemp(prefix="meeting-intelligence-"))
    output_template = download_dir / "audio.%(ext)s"
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-x",
        "--audio-format",
        "wav",
        "--no-playlist",
        "--proxy", os.getenv("MEETING_YT_PROXY", ""),
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
