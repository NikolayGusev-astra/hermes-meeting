"""Meeting Intelligence dashboard plugin backend — FastAPI router over the meeting artifacts folder.

Монтируется gateway на /api/plugins/meeting-intelligence/ когда плагин в plugins.enabled (config.yaml).
Работает внутри gateway-процесса (session auth автоматически).

Слой данных — файловая система: сканирует корень встреч (MEETING_ROOT, по умолчанию
C:\\Work\\Assist\\meeting) и возвращает список обработанных встреч и их артефактов
(транскрипты .txt, документы .docx/.xlsx). Роуты только на чтение.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# ── FastAPI (defensive: allow import for unit tests without dashboard deps) ──
try:
    from fastapi import APIRouter, HTTPException
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


# Корень с обработанными встречами. Переопределяется через MEETING_ROOT (например,
# при переносе на другой диск). По умолчанию — стандартная рабочая папка проекта.
def _meeting_root() -> Path:
    root = os.environ.get("MEETING_ROOT", r"C:\Work\Assist\meeting")
    return Path(root)


_OUTPUT_EXTS = {".docx", ".xlsx", ".pdf"}
_TRANSCRIPT_EXTS = {".txt"}
_IGNORE = {"generate_docs.py", "part1.transcript.transcript.json", "part2.transcript.transcript.json"}


def _artifact(file: Path) -> dict:
    ext = file.suffix.lower()
    kind = "docx" if ext in (".docx", ".xlsx", ".pdf") else ("txt" if ext == ".txt" else "other")
    return {
        "file": file.name,
        "kind": kind,
        "ext": ext.lstrip("."),
        "path": str(file),
        "size": file.stat().st_size,
    }


def _meeting_dir(dirpath: Path) -> dict | None:
    """Собрать карточку встречи из каталога (только если в нём есть выходные артефакты)."""
    try:
        files = [p for p in dirpath.iterdir() if p.is_file()]
    except OSError:
        return None
    artifacts = [_artifact(f) for f in files if f.name not in _IGNORE and f.suffix.lower() in (_OUTPUT_EXTS | _TRANSCRIPT_EXTS)]
    if not artifacts:
        return None
    artifacts.sort(key=lambda a: (a["kind"] != "docx" and a["kind"] != "xlsx", a["file"]))
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
