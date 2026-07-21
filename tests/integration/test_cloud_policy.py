import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from meeting_intelligence.cli import enforce_cloud_policy


def test_blocks_cloud_by_default():
    os.environ["MEETING_ALLOW_CLOUD"] = "false"
    os.environ["MEETING_LLM_BASE_URL"] = "https://api.openai.com/v1"
    try:
        enforce_cloud_policy(False)
    except SystemExit as e:
        assert e.code == 2


def test_allows_loopback():
    os.environ["MEETING_ALLOW_CLOUD"] = "false"
    os.environ["MEETING_LLM_BASE_URL"] = "http://localhost:1234/v1"
    enforce_cloud_policy(False)


def test_allows_cloud_when_explicit():
    os.environ["MEETING_ALLOW_CLOUD"] = "false"
    os.environ["MEETING_LLM_BASE_URL"] = "https://api.openai.com/v1"
    enforce_cloud_policy(True)
