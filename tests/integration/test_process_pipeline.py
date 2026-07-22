import json
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from meeting_intelligence import cli


def _write_tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\x00\x00" * 160)


def _protocol(source_quote: str) -> dict:
    return {
        "participants": [{"name": "SPEAKER_00", "source_quote": source_quote}],
        "agenda": [],
        "decisions": [],
        "assignments": [],
        "open_questions": [],
        "unclear": [],
    }


def _run_process(monkeypatch, wav_path: Path, *extra_args: str) -> int:
    monkeypatch.setattr(cli, "translate_lines", lambda lines, target_lang, allow_cloud: lines)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "meeting",
            "process",
            str(wav_path),
            "--stt-model",
            "tiny",
            "--llm-model",
            "qwen2.5-7b-instruct",
            *extra_args,
        ],
    )
    return cli.main()


@pytest.mark.slow
def test_process_creates_transcript_and_protocol_from_tiny_wav(tmp_path, monkeypatch):
    wav_path = tmp_path / "meeting.wav"
    _write_tiny_wav(wav_path)
    calls = {}
    monkeypatch.setattr(cli, "check_resource_limits", lambda _: None)

    def fake_transcribe(audio, model, language, device, compute_type):
        calls["transcribe"] = (audio, model)
        return "[00:00->00:01] SPEAKER_00 | We approve the plan.", {"duration": 1}

    def fake_protocol(transcript, model, allow_cloud):
        calls["protocol"] = (transcript, model, allow_cloud)
        return _protocol("We approve the plan.")

    monkeypatch.setattr(cli, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(cli, "build_protocol", fake_protocol)

    assert _run_process(monkeypatch, wav_path) == 0
    assert calls["transcribe"] == (wav_path, "tiny")
    assert calls["protocol"][1:] == ("qwen2.5-7b-instruct", False)
    assert wav_path.with_suffix(".transcript.txt").is_file()
    assert wav_path.with_suffix(".protocol.json").is_file()


@pytest.mark.slow
def test_process_replaces_speaker_label_with_participant_name(tmp_path, monkeypatch):
    wav_path = tmp_path / "meeting.wav"
    _write_tiny_wav(wav_path)
    transcript = "[00:00->00:01] SPEAKER_00 | Alice approves the plan."
    monkeypatch.setattr(cli, "check_resource_limits", lambda _: None)
    monkeypatch.setattr(cli, "transcribe_audio", lambda *args: (transcript, {"duration": 1}))
    monkeypatch.setattr(
        cli, "build_protocol", lambda *args, **kwargs: _protocol("Alice approves the plan.")
    )

    assert _run_process(monkeypatch, wav_path, "--participants", "SPEAKER_00=Alice") == 0

    protocol = json.loads(wav_path.with_suffix(".protocol.json").read_text(encoding="utf-8"))
    assert protocol["participants"][0]["name"] == "Alice"


@pytest.mark.slow
def test_process_strips_short_repeated_token_garbage(tmp_path, monkeypatch):
    wav_path = tmp_path / "meeting.wav"
    _write_tiny_wav(wav_path)
    transcript = "с с с с\n[00:00->00:01] SPEAKER_00 | Keep this line."
    monkeypatch.setattr(cli, "check_resource_limits", lambda _: None)
    monkeypatch.setattr(cli, "transcribe_audio", lambda *args: (transcript, {"duration": 1}))
    monkeypatch.setattr(
        cli, "build_protocol", lambda text, *args, **kwargs: _protocol("Keep this line.")
    )

    assert _run_process(monkeypatch, wav_path) == 0

    saved = wav_path.with_suffix(".transcript.txt").read_text(encoding="utf-8")
    assert "с с с с" not in saved
    assert "Keep this line." in saved


@pytest.mark.slow
def test_process_chunks_a_long_transcript(tmp_path, monkeypatch):
    wav_path = tmp_path / "meeting.wav"
    _write_tiny_wav(wav_path)
    transcript = "[00:00->00:01] SPEAKER_00 | " + ("word " * 6_000)
    chunks = []
    monkeypatch.setattr(cli, "check_resource_limits", lambda _: None)
    monkeypatch.setattr(cli, "transcribe_audio", lambda *args: (transcript, {"duration": 1}))
    monkeypatch.setenv("MEETING_PROTOCOL_CHUNK_SIZE", "100")

    def fake_chunk(chunk, *args):
        chunks.append(chunk)
        return _protocol("word")

    monkeypatch.setattr(cli, "_build_protocol_chunk", fake_chunk)

    assert _run_process(monkeypatch, wav_path) == 0
    assert len(chunks) > 1
