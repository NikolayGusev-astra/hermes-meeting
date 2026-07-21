import importlib.util
import os, sys, tempfile, wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

def _load_cli():
    spec = importlib.util.spec_from_file_location("meeting_intelligence.cli", Path(__file__).resolve().parents[2] / "src" / "meeting_intelligence" / "cli.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_small_wav_passes():
    mod = _load_cli()
    p = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    p.close()
    with wave.open(p.name, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    try:
        mod.check_resource_limits(Path(p.name))
    finally:
        os.unlink(p.name)

def test_too_long_wav_fails(monkeypatch):
    mod = _load_cli()
    p = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    p.close()
    with wave.open(p.name, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    try:
        duration = float(wave.open(p.name).getnframes() / 16000)
        try:
            mod.check_resource_limits(Path(p.name), max_duration_sec=max(0.1, duration - 0.5))
        except SystemExit:
            pass
        else:
            raise AssertionError("expected failure for long audio")
    finally:
        os.unlink(p.name)
