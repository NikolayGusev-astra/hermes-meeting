"""Tests for the web dashboard (jobs store + API endpoints)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))


# ── Job store unit tests ─────────────────────────────────────────────────


def test_job_store_create_and_get():
    from meeting_intelligence.web.jobs import JobStore, JobStatus

    store = JobStore()
    job = store.create("meeting.mp4", "upload", {"stt_model": "small"}, Path("/tmp"))
    assert job.id
    assert job.status == JobStatus.PENDING
    assert job.source_name == "meeting.mp4"

    fetched = store.get(job.id)
    assert fetched is job


def test_job_store_update_changes_status():
    from meeting_intelligence.web.jobs import JobStore, JobStatus

    store = JobStore()
    job = store.create("test.wav", "upload", {}, Path("/tmp"))
    store.update(job.id, status=JobStatus.RUNNING)
    assert store.get(job.id).status == JobStatus.RUNNING
    assert store.get(job.id).updated_at >= job.created_at


def test_job_store_get_missing_returns_none():
    from meeting_intelligence.web.jobs import JobStore

    store = JobStore()
    assert store.get("nonexistent") is None


# ── API endpoint tests (mocked pipeline) ─────────────────────────────────


@pytest.fixture()
def client(monkeypatch):
    """FastAPI TestClient with pipeline.process mocked."""
    from meeting_intelligence.web import jobs as jobs_mod
    from meeting_intelligence.pipeline import ProcessResult

    class FakeResult:
        transcript_path = Path("/tmp/fake.transcript.txt")
        transcript = "fake transcript"
        translated_path = None
        protocol_path = Path("/tmp/fake.protocol.json")
        protocol = {"quality": {"valid": True}}
        valid = True

    async def fake_run(job_id, source_path, params):
        jobs_mod.store.update(
            job_id,
            status=jobs_mod.JobStatus.DONE,
            result={
                "transcript_path": "/tmp/fake.transcript.txt",
                "translated_path": None,
                "protocol_path": "/tmp/fake.protocol.json",
                "valid": True,
                "files": [
                    {"name": "transcript", "label": "Transcript", "filename": "fake.transcript.txt"},
                ],
            },
        )

    monkeypatch.setattr(jobs_mod, "run_pipeline_job", fake_run)

    from fastapi.testclient import TestClient
    from meeting_intelligence.web.app import app

    return TestClient(app)


def test_dashboard_page_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Meeting Intelligence" in resp.text
    assert "Upload File" in resp.text


def test_create_job_requires_file_or_url(client):
    resp = client.post("/api/jobs", data={})
    assert resp.status_code == 400


def test_create_job_from_url(client):
    resp = client.post("/api/jobs", data={
        "url": "https://example.com/meeting.mp4",
        "stt_model": "small",
        "language": "en",
    })
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["source_type"] == "url"
    assert body["id"]


def test_get_job_status(client):
    create = client.post("/api/jobs", data={"url": "https://example.com/m.wav"})
    job_id = create.json()["id"]

    # The mocked run_pipeline_job completes synchronously in the event loop
    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("pending", "running", "done")


def test_get_missing_job_404(client):
    resp = client.get("/api/jobs/nonexistent-id")
    assert resp.status_code == 404


def test_download_rejects_unknown_filename(client):
    create = client.post("/api/jobs", data={"url": "https://example.com/m.wav"})
    job_id = create.json()["id"]
    resp = client.get(f"/api/jobs/{job_id}/files/evil.exe")
    assert resp.status_code in (404, 409)
