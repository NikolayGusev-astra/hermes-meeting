"""Unit tests for Telegram voice ingest (ADR-010 / SDD v0.9.0).

Offline: telethon and Whisper are mocked. Covers source filtering,
DM speaker attribution from TG metadata, and meeting grouping.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from meeting_intelligence import ingest, sources
from meeting_intelligence.transcribe import transcribe_audio


# ── Fixtures ──────────────────────────────────────────────────────────────

def _msg_voice(msg_id, date, out, sender_name="Evgenius", duration=10):
    """Minimal fake Message with .voice and metadata."""
    class Attr:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
    voice = Attr(duration=duration, size=1000, attributes=[])
    sender = Attr(first_name=sender_name, username="evg")
    msg = Attr(
        id=msg_id, date=date, out=out, sender=sender, voice=voice,
        video=None,
    )
    return msg


def _msg_text(msg_id, date, out):
    class Attr:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
    sender = Attr(first_name="Evgenius", username="evg")
    return Attr(id=msg_id, date=date, out=out, sender=sender,
                voice=None, video=None)


# ── Source filtering & attribution ────────────────────────────────────────

class TestResolveTgSource:
    def test_filters_only_voice_and_round(self, tmp_path):
        """extract_tg_voice_refs keeps only voice/round, attributes DM speaker."""
        import asyncio
        from datetime import datetime, timezone
        from types import SimpleNamespace

        from meeting_intelligence.sources import extract_tg_voice_refs

        def _msg(mid, out, name="Evgenius", dur=10, has_voice=True, round_vid=False):
            voice = (
                SimpleNamespace(duration=dur, size=1000, attributes=[])
                if has_voice else None
            )
            video = (
                SimpleNamespace(round_message=True, duration=dur, attributes=[])
                if round_vid else None
            )
            sender = SimpleNamespace(first_name=name, username="evg")
            return SimpleNamespace(
                id=mid,
                date=datetime(2026, 8, 5, 16, 50, 6, tzinfo=timezone.utc),
                out=out, sender=sender, voice=voice, video=video,
            )

        v1 = _msg(101, False, "Evgenius")
        v2 = _msg(102, True, "Nikolay")  # out=True -> owner
        txt = _msg(103, False, has_voice=False)  # text -> dropped
        messages = [v1, v2, txt]

        refs = asyncio.run(extract_tg_voice_refs(messages, "Nikolay", tmp_path))
        ids = sorted(r.msg_id for r in refs)
        assert ids == [101, 102], f"expected only voice msgs, got {ids}"
        by_id = {r.msg_id: r for r in refs}
        assert by_id[101].sender_label == "Evgenius"
        assert by_id[102].sender_label == "Nikolay"

    def test_missing_session_fails(self, monkeypatch, tmp_path):
        import pytest
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        # No session file -> fail()
        with pytest.raises(SystemExit):
            sources.resolve_tg_source("X", output_dir=tmp_path)


# ── DM speaker tagging in transcribe_audio ────────────────────────────────

class TestTranscribeSpeakerLabel:
    def test_speaker_label_skips_diarization(self, monkeypatch):
        # Stub WhisperModel so no real model loads
        class FakeSeg:
            def __init__(self, start, end, text):
                self.start, self.end, self.text = start, end, text
        class FakeModel:
            def __init__(self, *a, **k):
                pass
            def transcribe(self, *a, **k):
                info = SimpleNamespace(language="ru", duration=9.8,
                                        language_probability=0.99, no_speech_prob=0.0)
                return iter([FakeSeg(0.0, 2.0, "привет"), FakeSeg(2.1, 4.0, "ека")]), info
        import types
        fake_fw = types.SimpleNamespace(WhisperModel=FakeModel)
        monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)

        transcript, meta = transcribe_audio(
            Path("dummy.ogg"), "small", "ru", "cpu", "int8",
            speaker_label="Evgenius",
        )
        assert meta["diarization"] == "tg-sender:Evgenius"
        assert all("Evgenius |" in line for line in transcript.splitlines())
        assert "SPEAKER_" not in transcript


# ── Meeting grouping ──────────────────────────────────────────────────────

class TestGroupIntoMeetings:
    def test_day_boundary_splits_meetings(self):
        refs = [
            _ref(1, 2026, 8, 5, 10, 0),
            _ref(2, 2026, 8, 5, 11, 0),
            _ref(3, 2026, 8, 6, 10, 0),
        ]
        meetings = ingest.group_into_meetings(refs)
        assert len(meetings) == 2
        assert [len(m.utterances) for m in meetings] == [2, 1]

    def test_gap_within_day_splits_session(self):
        # 10:00 and 10:30 -> same (gap 30m < 120m); 14:00 -> new (gap 210m)
        refs = [
            _ref(1, 2026, 8, 5, 10, 0),
            _ref(2, 2026, 8, 5, 10, 30),
            _ref(3, 2026, 8, 5, 14, 0),
        ]
        meetings = ingest.group_into_meetings(refs, gap_minutes=120)
        assert len(meetings) == 2
        assert [len(m.utterances) for m in meetings] == [2, 1]


def _ref(msg_id, y, mo, d, h, mi):
    from meeting_intelligence.ingest import TgVoiceRef
    return TgVoiceRef(
        msg_id=msg_id,
        date=datetime(y, mo, d, h, mi, tzinfo=timezone.utc),
        sender_label="Evgenius",
        is_out=False,
        ogg_path=Path(f"{msg_id}.ogg"),
        duration_sec=10,
    )
