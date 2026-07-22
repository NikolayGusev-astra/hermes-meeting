import subprocess
import sys
from pathlib import Path


def run(args, cwd=None):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=cwd)


pkg = Path(__file__).resolve().parents[1] / "src" / "meeting_intelligence"
cli = pkg / "__main__.py"
assert cli.exists(), cli
assert (
    run(["-m", "meeting_intelligence", "--help"], cwd=str(pkg.parent.parent)).returncode
    == 0
)
print("smoke ok")
