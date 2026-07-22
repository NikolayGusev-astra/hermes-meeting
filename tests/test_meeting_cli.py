import os
import json
import subprocess
import sys
from pathlib import Path

cli = Path(__file__).resolve().parents[1] / "src" / "meeting_intelligence" / "__main__.py"
root = Path(__file__).resolve().parents[1]
env = {**os.environ, "PYTHONPATH": str(root / "src")}


def run(args):
    return subprocess.run(
        [sys.executable, "-m", "meeting_intelligence", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
    )


def test_help():
    rc = run(["--help"])
    assert rc.returncode == 0
    assert "transcribe" in rc.stdout


def test_transcribe_help():
    rc = run(["transcribe", "--help"])
    assert rc.returncode == 0


def test_translate_help():
    rc = run(["translate", "--help"])
    assert rc.returncode == 0


def test_agent_transcript_outputs_cleaned_json(tmp_path):
    transcript = tmp_path / "meeting.txt"
    transcript.write_text(
        "[seg_0001] [00:00->00:01] SPEAKER_00 | Hello\n"
        + " ".join(["a"] * 5)
        + "\nsegment_0002: [00:01->00:02] SPEAKER_01 | Goodbye\n",
        encoding="utf-8",
    )

    rc = run(["agent-transcript", str(transcript)])

    assert rc.returncode == 0
    payload = json.loads(rc.stdout)
    assert payload["transcript"] == (
        "[00:00->00:01] SPEAKER_00 | Hello\n[00:01->00:02] SPEAKER_01 | Goodbye"
    )
    assert payload["metadata"]["garbage_lines_removed"] == 1
    assert payload["metadata"]["segment_ids_stripped"] == 2
    assert payload["metadata"]["llm_called"] is False


def test_protocol_help():
    rc = run(["protocol", "--help"])
    assert rc.returncode == 0


def test_process_help():
    rc = run(["process", "--help"])
    assert rc.returncode == 0


def test_transcribe_missing_file():
    rc = run(["transcribe", "/tmp/nonexistent.wav"])
    assert rc.returncode == 2
    assert "File not found" in rc.stderr


def test_translate_missing_file():
    rc = run(["translate", "/tmp/nonexistent.txt"])
    assert rc.returncode == 2
    assert "Transcript not found" in rc.stderr


def test_protocol_missing_file():
    rc = run(["protocol", "/tmp/nonexistent.txt"])
    assert rc.returncode == 2
    assert "Transcript not found" in rc.stderr


def test_process_missing_file():
    rc = run(["process", "/tmp/nonexistent.mp4"])
    assert rc.returncode == 2
    assert "File not found" in rc.stderr
