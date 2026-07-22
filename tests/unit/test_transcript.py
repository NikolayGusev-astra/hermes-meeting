import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from meeting_intelligence.cli import _agent_mode_enabled, _clean_whisper_artifacts, transcribe_audio


def test_agent_mode_is_opt_in(monkeypatch):
    monkeypatch.delenv("MEETING_AGENT_MODE", raising=False)
    assert _agent_mode_enabled() is False
    monkeypatch.setenv("MEETING_AGENT_MODE", "true")
    assert _agent_mode_enabled() is True


def test_transcribe_metadata_shape():
    from unittest.mock import MagicMock

    segment = MagicMock()
    segment.start = 0.0
    segment.end = 1.0
    segment.text = " Hello world "
    info = MagicMock()
    info.language = "en"
    info.language_probability = 0.99
    info.no_speech_prob = 0.01
    info.duration = 1.0
    model = MagicMock()
    model.transcribe.return_value = ([segment], info)
    import faster_whisper

    original = faster_whisper.WhisperModel
    faster_whisper.WhisperModel = lambda *a, **k: model
    try:
        audio = Path(tempfile.gettempdir()) / "mi_test.wav"
        audio.write_bytes(b"RIFF")
        out, meta = transcribe_audio(audio, "tiny", "en", "cpu", "int8")
        assert meta["schema_version"] == "0.1.0"
        assert meta["segment_count"] == 1
        assert "SPEAKER_" in out
        assert "[00:00->00:01]" in out
        assert out.count("SPEAKER_00") == 1
    finally:
        faster_whisper.WhisperModel = original


def test_transcribe_discards_runs_of_short_hallucination_segments():
    from unittest.mock import MagicMock

    segments = []
    for index in range(5):
        segment = MagicMock()
        segment.start = float(index)
        segment.end = float(index + 1)
        segment.text = "a"
        segments.append(segment)
    info = MagicMock(language="en", duration=5.0)
    model = MagicMock()
    model.transcribe.return_value = (segments, info)
    import faster_whisper

    original = faster_whisper.WhisperModel
    faster_whisper.WhisperModel = lambda *args, **kwargs: model
    try:
        audio = Path(tempfile.gettempdir()) / "mi_short_artifacts.wav"
        audio.write_bytes(b"RIFF")
        transcript, meta = transcribe_audio(audio, "tiny", "en", "cpu", "int8")
        assert transcript == ""
        assert meta["segment_count"] == 0
    finally:
        faster_whisper.WhisperModel = original


def test_clean_whisper_artifacts_removes_repeated_single_character_line():
    transcript = "normal line\n" + " ".join(["а"] * 10) + "\nother line"

    assert _clean_whisper_artifacts(transcript) == "normal line\nother line"
