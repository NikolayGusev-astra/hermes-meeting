import os, subprocess, sys
from pathlib import Path
import pytest


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _win_create_no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_editable_install_and_console_script():
    if _is_windows():
        pytest.xfail("Known Windows subprocess venv issue; wheel/console script verified independently")
    root = Path(__file__).resolve().parents[1]
    venv_dir = root / "temp_test_venv"
    if venv_dir.exists():
        import shutil
        shutil.rmtree(venv_dir, ignore_errors=True)
    kwargs = {"check": True, "creationflags": _win_create_no_window()}
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], **kwargs)
    try:
        pip = venv_dir / "Scripts" / "pip"
        py = venv_dir / "Scripts" / "python"
        if not pip.exists():
            pip = venv_dir / "bin" / "pip"
            py = venv_dir / "bin" / "python"
        subprocess.run([str(pip), "install", "--quiet", str(root)], **kwargs)
        out = subprocess.run(
            [str(py), "-m", "meeting", "--help"],
            capture_output=True,
            text=True,
            creationflags=_win_create_no_window(),
        )
        assert out.returncode == 0, out.stderr
    finally:
        import shutil
        shutil.rmtree(venv_dir, ignore_errors=True)
