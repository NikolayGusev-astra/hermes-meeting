from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("meeting")


def _transcribe_default_device() -> str:
    """Auto-detect best available device: cuda > mps > rocm > cpu."""
    import platform as _platform

    try:
        from ctranslate2 import get_cuda_device_count as _cuda_count

        if _cuda_count() > 0:
            cublas_ok = False
            import ctypes as ctypes

            for dll in ("cublas64_12.dll", "cublas64_11.dll", "libcublas.so.12"):
                try:
                    ctypes.cdll.LoadLibrary(dll)
                    cublas_ok = True
                    break
                except OSError:
                    pass
            if not cublas_ok:
                try:
                    import nvidia.cublas

                    cublas = Path(nvidia.cublas.__path__[0]) / "bin" / "cublas64_12.dll"
                    ctypes.cdll.LoadLibrary(str(cublas))
                    cublas_ok = True
                except Exception:
                    pass
            if not cublas_ok:
                log.warning("CUDA GPU found but runtime missing. Install: pip install meeting-intelligence[gpu]")
                return "cpu"
            log.info("Auto-detected device: cuda")
            return "cuda"
    except Exception:
        pass

    if _platform.system() == "Darwin" and _platform.machine() == "arm64":
        log.info("Auto-detected device: cpu (Apple Silicon)")
    return "cpu"
