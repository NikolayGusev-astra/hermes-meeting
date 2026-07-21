import subprocess
import sys
from pathlib import Path

cli = Path(__file__).resolve().parents[1] / "scripts" / "meeting_cli.py"

def run(args):
    return subprocess.run([sys.executable, str(cli), *args], capture_output=True, text=True)

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
