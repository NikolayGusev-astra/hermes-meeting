"""FastAPI web dashboard for meeting intelligence.

Routes:
  GET  /                      — single-page dashboard
  POST /api/jobs              — create job (file upload OR url)
  GET  /api/jobs/{id}         — poll job status
  GET  /api/jobs/{id}/files/{filename}  — download output file
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .jobs import JobStatus, run_pipeline_job, store

TEMPLATES_DIR = Path(__file__).parent / "templates"
DATA_DIR = Path(tempfile.gettempdir()) / "meeting-intelligence-web"

app = FastAPI(title="Meeting Intelligence Dashboard", version="0.8.0")


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    """Serve the single-page dashboard."""
    html_path = TEMPLATES_DIR / "dashboard.html"
    if not html_path.exists():
        raise HTTPException(500, "dashboard.html template not found")
    return html_path.read_text(encoding="utf-8")


@app.post("/api/jobs", status_code=202)
async def create_job(
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    stt_model: str = Form("small"),
    llm_model: str = Form("qwen2.5-7b-instruct"),
    language: str = Form("en"),
    target_lang: str = Form("ru"),
    skip_translate: bool = Form(False),
    allow_cloud: bool = Form(False),
) -> JSONResponse:
    """Create a processing job from an uploaded file or a URL."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    params = {
        "stt_model": stt_model,
        "llm_model": llm_model,
        "language": language,
        "device": "cpu",
        "compute_type": "int8",
        "target_lang": target_lang,
        "skip_translate": skip_translate,
        "docx": True,
        "allow_cloud": allow_cloud,
    }

    if file is not None and file.filename:
        job_dir = DATA_DIR / f"job-{uuid.uuid4().hex[:12]}"
        job_dir.mkdir(parents=True, exist_ok=True)
        src_path = job_dir / file.filename
        with src_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        job = store.create(file.filename, "upload", params, job_dir)
        source_path = str(src_path)
        source_label = file.filename
    elif url:
        job_dir = DATA_DIR / f"job-{uuid.uuid4().hex[:12]}"
        job_dir.mkdir(parents=True, exist_ok=True)
        job = store.create(url, "url", params, job_dir)
        source_path = url
        source_label = url
    else:
        raise HTTPException(status_code=400, detail="Either 'file' or 'url' is required")

    asyncio.create_task(run_pipeline_job(job.id, source_path, params))
    return JSONResponse(job.to_dict(), status_code=202)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    """Poll job status and result."""
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(job.to_dict())


@app.get("/api/jobs/{job_id}/files/{filename}")
async def download_file(job_id: str, filename: str) -> FileResponse:
    """Download a generated output file for a completed job."""
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=409, detail="Job is not done yet")

    # Security: only allow files that appear in the job result's file list
    allowed = {f["filename"] for f in (job.result or {}).get("files", [])}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="File not available for this job")

    file_path = Path(job.output_dir) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(file_path, filename=filename)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> int:
    """Launch the uvicorn server. Called from `meeting serve`."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)
    return 0
