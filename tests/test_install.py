import os, subprocess, sys
from pathlib import Path

def test_editable_install_and_console_script():
    root = Path(__file__).resolve().parents[1]
    with subprocess.Popen([sys.executable, "-m", "venv", "temp_test_venv"], cwd=str(root)) as p:
        p.wait()
    try:
        v = root / "temp_test_venv"
        pip = v / "Scripts" / "pip"
        py = v / "Scripts" / "python"
        if not pip.exists():
            pip = v / "bin" / "pip"
            py = v / "bin" / "python"
        subprocess.run([str(pip), "install", "--quiet", str(root)], cwd=str(root), check=True)
        out = subprocess.run([str(py), "-m", "meeting", "--help"], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
    finally:
        import shutil
        shutil.rmtree(root / "temp_test_venv", ignore_errors=True)
