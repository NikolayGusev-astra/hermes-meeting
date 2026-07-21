import subprocess, sys
from pathlib import Path

def run(args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True)

cli = Path(__file__).resolve().parents[1] / "scripts" / "meeting_cli.py"
assert cli.exists(), cli
assert run([str(cli), "--help"]).returncode == 0
print("smoke ok")
