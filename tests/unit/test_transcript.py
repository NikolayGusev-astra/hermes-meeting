import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from meeting_intelligence.cli import transcribe_audio


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
