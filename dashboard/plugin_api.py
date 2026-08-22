"""Meeting Intelligence dashboard plugin backend — FastAPI router over the meeting artifacts folder.

Монтируется gateway на /api/plugins/meeting-intelligence/ когда плагин в plugins.enabled (config.yaml).
Работает внутри gateway-процесса (session auth автоматически).

Слой данных — файловая система: сканирует корень встреч (MEETING_ROOT, по умолчанию
C:\\Work\\Assist\\meeting) и возвращает список обработанных встреч и их артефактов
(транскрипты .txt, документы .docx/.xlsx). Роуты только на чтение.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# plugin_api грузится gateway standalone (importlib из dashboard/), не как часть
# пакета — добавим src/ на sys.path, чтобы `from meeting_intelligence import ...`
# работало в обработчиках (voiceprints и т.п.).
_PLUGIN_SRC = Path(__file__).resolve().parent.parent / "src"
if _PLUGIN_SRC.is_dir() and str(_PLUGIN_SRC) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_SRC))

# ── FastAPI (defensive: allow import for unit tests without dashboard deps) ──
try:
    from fastapi import APIRouter, Body, HTTPException
    from fastapi.responses import FileResponse
except Exception:  # Allows local unit tests without dashboard dependencies.
    class APIRouter:  # type: ignore
        def get(self, *a, **k):
            return lambda fn: fn
        def post(self, *a, **k):
            return lambda fn: fn
        def put(self, *a, **k):
            return lambda fn: fn
        def delete(self, *a, **k):
            return lambda fn: fn
    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int, detail: Any = None):
            self.status_code = status_code
            self.detail = detail
    class FileResponse:  # type: ignore
        def __init__(self, *a, **k):
            raise RuntimeError("fastapi.responses.FileResponse unavailable")


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))


def _storage_config_path() -> Path:
    return _hermes_home() / "meeting-storage.json"


def load_storage_config() -> dict:
    try:
        p = _storage_config_path()
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def save_storage_config(root: str) -> dict:
    cfg = {"root": str(root)}
    p = _storage_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


# Корень с обработанными встречами: конфиг (storage/config) > MEETING_ROOT env > дефолт.
def _meeting_root() -> Path:
    cfg = load_storage_config()
    if cfg.get("root"):
        return Path(cfg["root"])
    return Path(os.environ.get("MEETING_ROOT", r"C:\Work\Assist\meeting"))


_OUTPUT_EXTS = {".docx", ".xlsx", ".pdf"}
_TRANSCRIPT_EXTS = {".txt"}
_AUDIO_VIDEO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".mp4", ".mkv", ".mov", ".webm"}
_IGNORE = {"generate_docs.py", "part1.transcript.transcript.json", "part2.transcript.transcript.json"}


def _artifact(file: Path) -> dict:
    ext = file.suffix.lower()
    if ext in (".docx", ".xlsx", ".pdf"):
        kind = "docx"
    elif ext == ".txt":
        kind = "txt"
    elif ext in _AUDIO_VIDEO_EXTS:
        kind = "original"
    else:
        kind = "other"
    try:
        subdir = file.parent.name if file.parent.name != file.parent.parent.name else ""
    except Exception:
        subdir = ""
    return {
        "file": file.name,
        "kind": kind,
        "ext": ext.lstrip("."),
        "path": str(file),
        "size": file.stat().st_size,
        "subdir": subdir,
    }


def _meeting_dir(dirpath: Path) -> dict | None:
    """Собрать карточку встречи из каталога (рекурсивно; только если есть артефакты)."""
    try:
        files = [p for p in dirpath.rglob("*") if p.is_file()]
    except OSError:
        return None
    artifacts = [_artifact(f) for f in files if f.name not in _IGNORE and f.suffix.lower() in (_OUTPUT_EXTS | _TRANSCRIPT_EXTS | _AUDIO_VIDEO_EXTS)]
    if not artifacts:
        return None
    artifacts.sort(key=lambda a: (a["kind"] == "original", a["kind"] == "txt", a["file"]))
    return {
        "name": dirpath.name,
        "date": dirpath.name[:10] if len(dirpath.name) >= 10 else "",
        "path": str(dirpath),
        "file_count": len(artifacts),
        "artifacts": artifacts,
    }


router = APIRouter()


@router.get("/meetings")
def list_meetings():
    """Список обработанных встреч (каталоги с артефактами), новые сверху."""
    root = _meeting_root()
    if not root.exists() or not root.is_dir():
        return {"root": str(root), "meetings": [], "error": f"meeting root not found: {root}"}
    meetings = []
    try:
        for child in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
            if child.is_dir():
                card = _meeting_dir(child)
                if card:
                    meetings.append(card)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"cannot scan {root}: {e}")
    return {"root": str(root), "meetings": meetings}


@router.get("/meetings/{name}")
def get_meeting(name: str):
    """Карточка конкретной встречи по имени каталога (path-traversal защищён)."""
    root = _meeting_root()
    safe = Path(name).name
    target = (root / safe).resolve()
    if not str(target).startswith(str(root.resolve())) or not target.is_dir():
        raise HTTPException(status_code=404, detail="meeting not found")
    card = _meeting_dir(target)
    if not card:
        raise HTTPException(status_code=404, detail="meeting has no artifacts")
    return card


@router.get("/state")
def get_state():
    """Псевдоним list_meetings — один запрос для UI-дашборда."""
    return list_meetings()


@router.get("/storage/config")
def storage_config_get():
    """Текущий корень хранилища (config > MEETING_ROOT env > дефолт) + каталог спикеров."""
    cfg = load_storage_config()
    root = _meeting_root()
    return {"configured": bool(cfg.get("root")), "root": str(root), "speakers_dir": str(root / "speakers")}


@router.post("/storage/config")
def storage_config_set(body: dict = Body(default={})):
    """Выбрать корень хранилища и создать структуру (каталог speakers/ — глобальные профили).

    Per-meeting структура (оригинал/транскрипция/документы) создаётся при обработке
    каждой встречи агентом; здесь — только корень + глобальный speakers/.
    """
    root = str((body or {}).get("root", "")).strip()
    if not root:
        raise HTTPException(status_code=400, detail="root required")
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    (root_path / "speakers").mkdir(exist_ok=True)
    cfg = save_storage_config(str(root_path))
    return {"ok": True, **cfg, "speakers_dir": str(root_path / "speakers")}


@router.get("/storage/status")
def storage_status():
    """Сводка: размер встреч + место на диске (два независимых показателя).

    free_pct — процент всего диска; low_space считается и по проценту (<15%),
    и по абсолюту (<20 ГБ), чтобы диск на 2 ТБ не «краснел» при 7%.
    """
    root = _meeting_root()
    used = 0
    meetings = 0
    if root.exists():
        for child in root.iterdir():
            if child.is_dir():
                meetings += 1
                for f in child.rglob("*"):
                    try:
                        if f.is_file():
                            used += f.stat().st_size
                    except OSError:
                        pass
    try:
        du = shutil.disk_usage(str(root))
        total, free = du.total, du.free
        free_pct = round(100 * free / total, 1) if total else None
    except Exception:
        total = free = 0
        free_pct = None
    FREE_ABS_MIN = 20 * 1024**3  # 20 GB
    low_space = (
        free_pct is not None and free_pct < 15
    ) or (free and free < FREE_ABS_MIN)
    return {
        "root": str(root),
        "meetings": meetings,
        "used_bytes": used,
        "total_bytes": total,
        "free_bytes": free,
        "free_pct": free_pct,
        "low_space": low_space,
    }


def _safe_within(child: Path, root: Path) -> bool:
    """True если path `child` (уже resolved) лежит внутри `root` (resolved)."""
    try:
        child.relative_to(root)
        return True
    except ValueError:
        return False


_SPEAKER_LINE_RE = re.compile(r"^\[(\d{1,2}:\d{2})->(\d{1,2}:\d{2})\]\s+(\S+)\s+\|\s*(.*)$")


def _mmss_to_sec(value: str) -> float:
    minutes, seconds = value.strip().split(":", 1)
    return float(int(minutes) * 60 + int(seconds))


def _meeting_path(name: str) -> Path | None:
    root = _meeting_root().resolve()
    meeting = (root / Path(name).name).resolve()
    return meeting if _safe_within(meeting, root) and meeting.is_dir() else None


def _meeting_transcript_path(name: str) -> Path | None:
    meeting = _meeting_path(name)
    if meeting is None:
        return None
    try:
        for path in meeting.rglob("*.txt"):
            try:
                if any(_SPEAKER_LINE_RE.match(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()):
                    return path
            except OSError:
                continue
    except OSError:
        pass
    return None


def _meeting_source_audio(name: str) -> Path | None:
    meeting = _meeting_path(name)
    if meeting is None:
        return None
    try:
        files = [path for path in meeting.rglob("*") if path.is_file() and path.suffix.lower() in _AUDIO_VIDEO_EXTS]
    except OSError:
        return None
    if not files:
        return None
    wavs = [path for path in files if path.suffix.lower() == ".wav"]
    return max(wavs or files, key=lambda path: path.stat().st_size)


def _speaker_segments(transcript: Path, wanted_label: str | None = None) -> dict[str, dict]:
    speakers: dict[str, dict] = {}
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return speakers
    for line in lines:
        match = _SPEAKER_LINE_RE.match(line)
        if not match:
            continue
        start, end, label, text = match.groups()
        if wanted_label is not None and label != wanted_label:
            continue
        try:
            start_sec, end_sec = _mmss_to_sec(start), _mmss_to_sec(end)
        except (TypeError, ValueError):
            continue
        if end_sec < start_sec:
            continue
        item = speakers.setdefault(label, {"label": label, "segments": [], "sample_line": "", "count": 0, "total_dur_sec": 0.0})
        item["segments"].append([start_sec, end_sec])
        item["count"] += 1
        item["total_dur_sec"] += end_sec - start_sec
        if text.strip() and not item["sample_line"]:
            item["sample_line"] = text.strip()
    return speakers


def _extract_speaker_clip(audio_path: Path, segments: list, max_sec: float = 30.0) -> Path | None:
    """Extract selected speech intervals into a temporary WAV; caller removes its parent."""
    temp_dir = Path(tempfile.mkdtemp(prefix="meeting-speaker-"))
    parts: list[Path] = []
    try:
        elapsed = 0.0
        unlimited = max_sec == float("inf")
        for index, segment in enumerate(segments):
            if len(segment) < 2:
                continue
            start, end = float(segment[0]), float(segment[1])
            duration = max(0.0, end - start)
            if not unlimited:
                if elapsed >= max_sec:
                    break
                duration = min(duration, max_sec - elapsed)
            if duration <= 0:
                continue
            part = temp_dir / f"segment{index}.wav"
            result = subprocess.run(
                ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", str(audio_path), "-vn", "-c:a", "pcm_s16le", str(part)],
                capture_output=True, timeout=120, stdin=subprocess.DEVNULL,
            )
            if result.returncode != 0 or not part.exists():
                raise RuntimeError("ffmpeg could not extract speaker audio")
            parts.append(part)
            elapsed += duration
        if not parts:
            raise RuntimeError("no speaker audio segments")
        concat_list = temp_dir / "concat.txt"
        concat_list.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts), encoding="utf-8")
        output = temp_dir / "speaker.wav"
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c:a", "pcm_s16le", str(output)],
            capture_output=True, timeout=120, stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0 or not output.exists():
            raise RuntimeError("ffmpeg could not concatenate speaker audio")
        for path in parts + [concat_list]:
            path.unlink(missing_ok=True)
        return output
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None


def _remove_speaker_clip(clip: Path | None) -> None:
    if clip is not None:
        shutil.rmtree(clip.parent, ignore_errors=True)


@router.get("/meetings/{name}/speakers")
def get_meeting_speakers(name: str):
    transcript = _meeting_transcript_path(name)
    if transcript is None:
        return {"name": name, "speakers": [], "error": "no transcript"}
    speakers = _speaker_segments(transcript)
    return {"name": name, "speakers": list(speakers.values())}


@router.get("/meetings/{name}/speaker/{label}/audio")
def get_speaker_audio(name: str, label: str, max_sec: float = 30.0):
    transcript = _meeting_transcript_path(name)
    audio_path = _meeting_source_audio(name)
    if transcript is None or audio_path is None:
        raise HTTPException(status_code=404, detail="meeting transcript or audio not found")
    segments = _speaker_segments(transcript, label).get(label, {}).get("segments", [])
    if not segments:
        raise HTTPException(status_code=404, detail="speaker not found")
    clip = _extract_speaker_clip(audio_path, segments, max(0.0, max_sec))
    if clip is None:
        raise HTTPException(status_code=500, detail="could not extract speaker audio")
    try:
        import base64 as _b64
        data = clip.read_bytes()
        return {"filename": f"{Path(label).name}.wav", "size": len(data), "contentType": "audio/wav",
                "base64": _b64.b64encode(data).decode("ascii")}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"could not read speaker audio: {exc}")
    finally:
        _remove_speaker_clip(clip)


@router.post("/meetings/{name}/speaker/{label}/label")
def label_speaker(name: str, label: str, body: dict = Body(default={})):
    payload = body or {}
    full_name = str(payload.get("full_name", "")).strip()
    role = str(payload.get("role", "")).strip()
    contact = str(payload.get("contact", "")).strip()
    short = str(payload.get("short", "")).strip()
    if not short:
        raise HTTPException(status_code=400, detail="short required")
    transcript = _meeting_transcript_path(name)
    audio_path = _meeting_source_audio(name)
    if transcript is None or audio_path is None:
        raise HTTPException(status_code=400, detail="meeting transcript or audio not found")
    segments = _speaker_segments(transcript, label).get(label, {}).get("segments", [])
    if not segments:
        raise HTTPException(status_code=400, detail="speaker not found")
    clip = _extract_speaker_clip(audio_path, segments, float("inf"))
    if clip is None:
        raise HTTPException(status_code=400, detail="could not extract speaker audio")
    try:
        from meeting_intelligence import voiceprints
        vector = voiceprints.compute_speaker_embedding_from_audio(clip, device="cuda")
        voiceprints.save_profile(short, full_name, role, contact, vector, source_meeting=name)
        voiceprints.save_voiceprint(short, vector)
        profile = voiceprints.load_profiles().get(short, {})
        voiceprints.write_profile_md(short, profile)
        wiki_synced = bool(voiceprints.sync_to_wiki(short))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"could not label speaker: {exc}")
    finally:
        _remove_speaker_clip(clip)
    return {"ok": True, "short": short, "full_name": full_name, "wiki_synced": wiki_synced}


@router.get("/meetings/{name}/file/{filename}")
def get_meeting_file(name: str, filename: str):
    """Отдать байты артефакта встречи для открытия/скачивания из UI.

    Path-traversal защищён дважды: берём только basename имени каталога и файла
    (любые '..' / '/' обрезаются) И проверяем, что resolved-путь остался внутри
    resolved-корня. Отдаём только «артефактные» расширения (документы/транскрипты),
    чтобы не светить служебные файлы (generate_docs.py и т.п.).
    """
    root = _meeting_root().resolve()
    safe_name = Path(name).name
    meeting = (root / safe_name).resolve()
    if not _safe_within(meeting, root) or not meeting.is_dir():
        raise HTTPException(status_code=404, detail="meeting not found")

    safe_file = Path(filename).name  # обрезает любые каталоги/обходы
    target = (meeting / safe_file).resolve()
    if not _safe_within(target, meeting) or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    if target.name in _IGNORE or target.suffix.lower() not in (_OUTPUT_EXTS | _TRANSCRIPT_EXTS):
        raise HTTPException(status_code=404, detail="file not found")

    return FileResponse(str(target), filename=safe_file)


@router.get("/meetings/{name}/file/{filename}/data")
def get_meeting_file_data(name: str, filename: str):
    """Файл как base64 — для скачивания через авторизованный ctx.rest (JSON-мост).

    Прямой <a href> на /file/ не проходит auth/origin в desktop-вьюпорте, поэтому
    UI тащит файл этим роутом (через authed ctx.rest) и собирает Blob на клиенте.
    """
    import base64 as _b64
    root = _meeting_root().resolve()
    safe_name = Path(name).name
    meeting = (root / safe_name).resolve()
    if not _safe_within(meeting, root) or not meeting.is_dir():
        raise HTTPException(status_code=404, detail="meeting not found")
    safe_file = Path(filename).name
    target = (meeting / safe_file).resolve()
    if not _safe_within(target, meeting) or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    if target.name in _IGNORE or target.suffix.lower() not in (_OUTPUT_EXTS | _TRANSCRIPT_EXTS):
        raise HTTPException(status_code=404, detail="file not found")
    ext = target.suffix.lower()
    ct = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf": "application/pdf",
        ".txt": "text/plain; charset=utf-8",
        ".srt": "application/x-subrip",
        ".vtt": "text/vtt",
    }.get(ext, "application/octet-stream")
    data = target.read_bytes()
    return {"filename": safe_file, "size": len(data), "contentType": ct,
            "base64": _b64.b64encode(data).decode("ascii")}


# ── Обновление плагина: git-чек + ре-деплой виджета ─────────────────────
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _git_update_status(root):
    """Проверить git-remote на новые коммиты (с git fetch)."""
    def _g(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=20, stdin=subprocess.DEVNULL)
    try:
        _g("fetch", "-q")
    except Exception:
        pass
    try:
        cur = _g("rev-parse", "--short", "HEAD").stdout.strip() or "?"
        bo = _g("rev-list", "--count", "HEAD..@{u}")
        behind = int(bo.stdout.strip()) if (bo.returncode == 0 and bo.stdout.strip().isdigit()) else 0
        log = []
        if behind > 0:
            lg = _g("log", "--oneline", "-5", "HEAD..@{u}")
            log = [ln for ln in lg.stdout.splitlines() if ln.strip()]
        return {"current": cur, "behind": behind, "updates_available": behind > 0, "log": log}
    except Exception as e:
        return {"current": "?", "behind": 0, "updates_available": False, "log": [], "error": str(e)}


@router.get("/update/status")
def update_status():
    """Есть ли новые коммиты в git-remote (с git fetch)."""
    return _git_update_status(_PLUGIN_ROOT)


@router.post("/update/redeploy")
def update_redeploy():
    """Пере-деплой desktop-виджета после pull (hermes plugins update не копирует виджет)."""
    script = _PLUGIN_ROOT / "scripts" / "deploy-desktop-plugin.sh"
    if not script.exists():
        return {"ok": False, "err": "scripts/deploy-desktop-plugin.sh not found"}
    try:
        r = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=90, stdin=subprocess.DEVNULL)
        return {"ok": r.returncode == 0, "rc": r.returncode,
                "stdout": (r.stdout or "")[-800:], "stderr": (r.stderr or "")[-400:]}
    except Exception as e:
        return {"ok": False, "err": str(e)}


@router.post("/update/apply")
def update_apply():
    """git pull --autostash + ре-деплой виджета (обновление одним запросом)."""
    r = subprocess.run(["git", "-C", str(_PLUGIN_ROOT), "pull", "--ff-only", "--autostash"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=120, stdin=subprocess.DEVNULL)
    pulled_ok = r.returncode == 0
    redeployed = False
    script = _PLUGIN_ROOT / "scripts" / "deploy-desktop-plugin.sh"
    if script.exists():
        try:
            rd = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=90, stdin=subprocess.DEVNULL)
            redeployed = rd.returncode == 0
        except Exception:
            pass
    return {"ok": pulled_ok, "redeployed": redeployed,
            "stdout": (r.stdout or "")[-600:], "stderr": (r.stderr or "")[-300:]}
