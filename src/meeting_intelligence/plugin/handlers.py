"""Tool handlers returning structured JSON for Hermes."""
from __future__ import annotations

import subprocess
from typing import Any


def _run(argv):
    p = subprocess.run(argv, capture_output=True, text=True)
    return {"exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}


def transcribe(source: str) -> dict:
    return _run(["python", "scripts/meeting_cli.py", "transcribe", source])


def translate(transcript: str) -> dict:
    return _run(["python", "scripts/meeting_cli.py", "translate", transcript])


def protocol(transcript: str) -> dict:
    return _run(["python", "scripts/meeting_cli.py", "protocol", transcript])


def process(source: str) -> dict:
    return _run(["python", "scripts/meeting_cli.py", "process", source])
