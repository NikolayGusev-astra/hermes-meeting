import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from meeting_intelligence import attribution
from meeting_intelligence.pipeline import apply_speaker_mapping


def _response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_attribute_speakers_returns_valid_llm_mapping(monkeypatch):
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_: _response(
                    '```json\n{"SPEAKER_00": "Иван", "SPEAKER_01": "Ольга", "OTHER": "No"}\n```'
                )
            )
        )
    )
    monkeypatch.setattr(attribution, "OpenAI", lambda **_: client)

    result = attribution.attribute_speakers(
        "SPEAKER_00 | Привет, я Иван.\nSPEAKER_01 | Иван, это Ольга.",
        "local-model",
        allow_cloud=False,
    )

    assert result == {
        "ok": True,
        "mapping": {"SPEAKER_00": "Иван", "SPEAKER_01": "Ольга"},
        "err": None,
    }


def test_attribute_speakers_returns_failure_without_raising(monkeypatch):
    monkeypatch.setattr(attribution, "OpenAI", lambda **_: (_ for _ in ()).throw(RuntimeError("offline")))

    result = attribution.attribute_speakers("SPEAKER_00 | Привет", "local-model", False)

    assert result == {"ok": False, "mapping": {}, "err": "offline"}


def test_apply_speaker_mapping_replaces_protocol_people_fields():
    protocol = {
        "participants": [{"name": "SPEAKER_00"}],
        "decisions": [{"approved_by": ["SPEAKER_00", "SPEAKER_01"]}],
        "assignments": [{"assignee": "SPEAKER_01"}],
    }

    apply_speaker_mapping(protocol, {"SPEAKER_00": "Иван", "SPEAKER_01": "Ольга"})

    assert protocol == {
        "participants": [{"name": "Иван"}],
        "decisions": [{"approved_by": ["Иван", "Ольга"]}],
        "assignments": [{"assignee": "Ольга"}],
    }
