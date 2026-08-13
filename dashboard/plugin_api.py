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
import shutil
import subprocess
from pathlib import Path
from typing import Any

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
    """Сводка по размеру встреч + свободное место (предупреждение при <15%)."""
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
    return {
        "root": str(root),
        "meetings": meetings,
        "used_bytes": used,
        "total_bytes": total,
        "free_bytes": free,
        "free_pct": free_pct,
        "low_space": (free_pct is not None and free_pct < 15),
    }


def _safe_within(child: Path, root: Path) -> bool:
    """True если path `child` (уже resolved) лежит внутри `root` (resolved)."""
    try:
        child.relative_to(root)
        return True
    except ValueError:
        return False


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
