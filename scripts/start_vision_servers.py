# -*- coding: utf-8 -*-
"""Launch standalone llama.cpp vision servers for the meeting plugin.

Two servers, no LM Studio involved:
  - vision :8018 — LiquidAI LFM2.5-VL-3B (photo/interface descriptions)
  - ocr    :8017 — OvisOCR2 Q4_K_M + mmproj F16 (documents → Markdown)

Usage:
  python scripts/start_vision_servers.py            # both
  python scripts/start_vision_servers.py vision     # only :8018
  python scripts/start_vision_servers.py ocr        # only :8017

Env overrides:
  MEETING_LLAMA_SERVER   path to llama-server.exe
                         (default: newest LM Studio bundled CUDA build)
  MEETING_VISION_PORT / MEETING_OCR_PORT

Servers are started detached; this script exits after health-check passes.
Stop them with: taskkill /IM llama-server.exe /F  (kills both) or close the
spawned console windows.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LLAMA_SERVER = os.getenv(
    "MEETING_LLAMA_SERVER",
    r"C:\Users\n.gusev\.lmstudio\extensions\backends"
    r"\llama.cpp-win-x86_64-nvidia-cuda12-avx2-2.28.2\llama-server.exe",
)
MODELS = Path(os.getenv("MEETING_MODELS_DIR", r"C:\Users\n.gusev\.lmstudio\models"))

VL_GGUF = MODELS / "LiquidAI" / "LFM2.5-VL-3B-GGUF" / "LFM2.5-VL-3B-Q4_K_M.gguf"
VL_MMPROJ = MODELS / "LiquidAI" / "LFM2.5-VL-3B-GGUF" / "mmproj-LFM2.5-VL-3B-F16.gguf"
OCR_GGUF = MODELS / "Abiray_OvisOCR2-GGUF" / "OvisOCR2-Q4_K_M.gguf"
OCR_MMPROJ = MODELS / "Abiray_OvisOCR2-GGUF" / "mmproj-F16.gguf"

VISION_PORT = int(os.getenv("MEETING_VISION_PORT", "8018"))
OCR_PORT = int(os.getenv("MEETING_OCR_PORT", "8017"))

SPECS = {
    "vision": (VL_GGUF, VL_MMPROJ, VISION_PORT, "LFM2.5-VL-3B"),
    "ocr": (OCR_GGUF, OCR_MMPROJ, OCR_PORT, "OvisOCR2"),
}


def _already_up(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=2
        ) as r:
            return r.status == 200
    except Exception:
        return False


def launch(which: str) -> None:
    gguf, mmproj, port, name = SPECS[which]
    if _already_up(port):
        print(f"[{name}] already up on :{port}")
        return
    for p in (gguf, mmproj):
        if not Path(p).is_file():
            sys.exit(f"Missing model file: {p}")
    if not Path(LLAMA_SERVER).is_file():
        sys.exit(f"Missing llama-server: {LLAMA_SERVER}")

    cmd = [
        LLAMA_SERVER,
        "-m", str(gguf),
        "--mmproj", str(mmproj),
        "--port", str(port),
        "-ngl", "99",
        "-c", "8192",
        "--temp", "0",
    ]
    # CREATE_NEW_CONSOLE: лог сервера виден в отдельном окне, сервер
    # переживает закрытие родительского терминала.
    creationflags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
    # DLL: рядом с бинарником (ggml/cuda-обвязка) + CUDA runtime из
    # vendor-каталога LM Studio (cudart64_12, cublas64_12) — иначе WinError
    # 0xC0000135 (DLL not found), т.к. GUI обычно прописывает их сама.
    exe_dir = Path(LLAMA_SERVER).parent
    extra_dirs = [
        exe_dir,
        exe_dir.parent / "vendor" / "win-llama-cuda12-vendor-v2",
    ]
    child_env = dict(os.environ)
    additions = os.pathsep.join(str(d) for d in extra_dirs if d.is_dir())
    if additions:
        child_env["PATH"] = additions + os.pathsep + child_env.get("PATH", "")
    proc = subprocess.Popen(  # noqa: S603 (fixed argv, no shell)
        cmd, creationflags=creationflags,
        stdin=subprocess.DEVNULL,
        env=child_env,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        if _already_up(port):
            print(f"[{name}] up on :{port} (pid {proc.pid})")
            return
        if proc.poll() is not None:
            sys.exit(f"[{name}] llama-server exited early, code {proc.returncode}")
        time.sleep(1)
    sys.exit(f"[{name}] health-check timeout on :{port}")


if __name__ == "__main__":
    targets = sys.argv[1:] or ["vision", "ocr"]
    for t in targets:
        if t not in SPECS:
            sys.exit(f"Unknown target '{t}': use vision|ocr")
        launch(t)
