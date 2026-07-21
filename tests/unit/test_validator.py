import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from meeting_intelligence.cli import validate_protocol


def test_validator_rejects_fake_assignment():
    transcript = "Alice will review. Bob will deploy. Charlie will test."
    protocol = {
        "assignments": [
            {
                "task": "Transfer production secrets",
                "assignee": "Mallory",
                "deadline": "tomorrow",
                "source_quote": "Alpha Beta Gamma Delta",
            }
        ],
        "decisions": [],
        "participants": [],
    }
    result = validate_protocol(protocol, transcript)
    assert result["valid"] is False
    assert result["overall_confidence"] < 80


def test_validator_accepts_explicit_assignment():
    transcript = "Alice will review the PR by Friday."
    protocol = {
        "assignments": [
            {
                "task": "review the PR",
                "assignee": "Alice",
                "deadline": "Friday",
                "source_quote": "Alice will review the PR by Friday.",
            }
        ],
        "decisions": [],
        "participants": [],
    }
    result = validate_protocol(protocol, transcript)
    assert result["valid"] is True
    assert result["overall_confidence"] >= 80


def test_validator_rejects_partial_quote():
    transcript = "Alpha will review. Beta will deploy. Gamma will test."
    protocol = {
        "assignments": [
            {
                "task": "do something",
                "assignee": "Unknown",
                "deadline": "not_set",
                "source_quote": "Alpha Beta Gamma Delta Epsilon",
            }
        ],
        "decisions": [],
        "participants": [],
    }
    result = validate_protocol(protocol, transcript)
    assert result["valid"] is False


def test_validator_requires_assignee_grounding():
    transcript = "Alice will review the PR by Friday."
    protocol = {
        "assignments": [
            {
                "task": "review the PR",
                "assignee": "Mallory",
                "deadline": "Friday",
                "source_quote": "Alice will review the PR by Friday.",
            }
        ],
        "decisions": [],
        "participants": [],
    }
    result = validate_protocol(protocol, transcript)
    assert result["valid"] is False
    assert any("assignee not grounded" in e for e in result["errors"])


def test_validator_flags_fabricated_deadline():
    transcript = "Alice will review the PR by Friday."
    protocol = {
        "assignments": [
            {
                "task": "review the PR",
                "assignee": "Alice",
                "deadline": "next quarter",
                "source_quote": "Alice will review the PR by Friday.",
            }
        ],
        "decisions": [],
        "participants": [],
    }
    result = validate_protocol(protocol, transcript)
    assert any("deadline may be fabricated" in w for w in result["warnings"])
