"""In-memory job store for async pipeline execution.

The pipeline (Whisper transcription + LLM protocol) is slow — minutes per
meeting. We run it in a thread executor and expose status via polling.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from .. import pipeline
from ..pipeline import ProcessParams


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    status: JobStatus = JobStatus.PENDING
    source_name: str = ""
    source_type: str = ""  # "upload" | "url"
    params: dict = field(default_factory=dict)
    result: Optional[dict] = None
    error: Optional[str] = None
    output_dir: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status.value,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "result": self.result,
            "error": self.error,
            "output_dir": self.output_dir,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobStore:
    """Thread-safe-ish in-memory store (single-process uvicorn)."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(
        self,
        source_name: str,
        source_type: str,
        params: dict,
        output_dir: Path,
    ) -> Job:
        job_id = uuid.uuid4().hex[:12]
        now = _now()
        job = Job(
            id=job_id,
            source_name=source_name,
            source_type=source_type,
            params=params,
            output_dir=str(output_dir),
            created_at=now,
            updated_at=now,
        )
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs: object) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        for key, value in kwargs.items():
            setattr(job, key, value)
        job.updated_at = _now()


# Global singleton — persists across requests in a single uvicorn process.
store = JobStore()


def _collect_files(result: pipeline.ProcessResult, output_dir: Path) -> list[dict]:
    """Build a list of downloadable files from pipeline result."""
    files = []
    checks = [
        ("transcript", "Transcript (.txt)", result.transcript_path),
        ("translated", "Translation (.txt)", result.translated_path),
        ("protocol", "Protocol (.json)", result.protocol_path),
    ]
    for name, label, path in checks:
        if path and Path(path).exists():
            files.append({"name": name, "label": label, "filename": Path(path).name})

    # DOCX is written next to the source — scan output_dir for it
    for docx in output_dir.glob("*.docx"):
        files.append(
            {"name": f"docx_{docx.stem}", "label": f"DOCX ({docx.name})", "filename": docx.name}
        )
    return files


async def run_pipeline_job(job_id: str, source_path: str, params: dict) -> None:
    """Run the full pipeline in a thread executor, updating job status."""
    store.update(job_id, status=JobStatus.RUNNING)
    loop = asyncio.get_running_loop()

    def _run() -> pipeline.ProcessResult:
        return pipeline.process(
            ProcessParams(
                source=source_path,
                stt_model=params.get("stt_model", "small"),
                llm_model=params.get("llm_model", "qwen2.5-7b-instruct"),
                language=params.get("language", "en"),
                device=params.get("device", "cpu"),
                compute_type=params.get("compute_type", "int8"),
                target_lang=params.get("target_lang", "ru"),
                skip_translate=params.get("skip_translate", False),
                docx=params.get("docx", True),
                allow_cloud=params.get("allow_cloud", False),
            )
        )

    try:
        result = await loop.run_in_executor(None, _run)
        output_dir = Path(store.get(job_id).output_dir) if store.get(job_id) else Path(".")
        files = _collect_files(result, output_dir)
        store.update(
            job_id,
            status=JobStatus.DONE,
            result={
                "transcript_path": str(result.transcript_path),
                "translated_path": str(result.translated_path) if result.translated_path else None,
                "protocol_path": str(result.protocol_path) if result.protocol_path else None,
                "valid": result.valid,
                "files": files,
            },
        )
    except SystemExit as exc:
        code = int(exc.code) if exc.code is not None else 2
        store.update(job_id, status=JobStatus.ERROR, error=f"Pipeline exited with code {code}")
    except Exception as exc:
        store.update(job_id, status=JobStatus.ERROR, error=str(exc))
