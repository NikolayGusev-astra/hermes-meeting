import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from meeting_intelligence import cli


def test_build_protocol_chunks_and_deduplicates_overlapping_quotes(monkeypatch):
    calls = []

    def fake_build(chunk, model, allow_cloud):
        calls.append(chunk)
        if len(calls) == 1:
            return {
                "participants": [{"name": "Alice", "source_quote": "Alice"}],
                "agenda": [],
                "decisions": [{"text": "Ship it", "source_quote": "Ship it"}],
                "assignments": [],
                "open_questions": [],
                "unclear": [],
            }
        return {
            "participants": [{"name": "Alice", "source_quote": "Alice"}],
            "agenda": [],
            "decisions": [{"text": "Ship it", "source_quote": "Ship it"}],
            "assignments": [{"task": "Deploy", "source_quote": "Deploy"}],
            "open_questions": [],
            "unclear": [],
        }

    monkeypatch.setenv("MEETING_PROTOCOL_CHUNK_SIZE", "4000")
    monkeypatch.setattr(cli, "_build_protocol_chunk", fake_build)
    transcript = "A" * 24_001

    protocol = cli.build_protocol(transcript, "model", allow_cloud=False)

    assert len(calls) > 1
    assert all(calls)
    assert protocol["participants"] == [{"name": "Alice", "source_quote": "Alice"}]
    assert protocol["decisions"] == [{"text": "Ship it", "source_quote": "Ship it"}]
    assert protocol["assignments"] == [{"task": "Deploy", "source_quote": "Deploy"}]


def test_build_protocol_keeps_single_request_for_short_transcripts(monkeypatch):
    expected = {"decisions": [{"text": "Ship it", "source_quote": "Ship it"}]}
    monkeypatch.setattr(cli, "_build_protocol_chunk", lambda *args: expected)

    assert cli.build_protocol("short transcript", "model", allow_cloud=False) == expected
