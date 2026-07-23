import os
import subprocess
import sys
from pathlib import Path


def run(args, cwd=None):
    root = Path(__file__).resolve().parents[1]
    env = os.environ | {"PYTHONPATH": str(root / "src")}
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, cwd=cwd, env=env
    )


def test_package_smoke():
    root = Path(__file__).resolve().parents[1]
    version_check = run(
        [
            "-c",
            "import meeting_intelligence; "
            "assert meeting_intelligence.__version__ == '0.7.0'",
        ],
        cwd=root,
    )
    assert version_check.returncode == 0, version_check.stderr

    cli_check = run(["-m", "meeting_intelligence", "--help"], cwd=root)
    assert cli_check.returncode == 0, cli_check.stderr
