"""Hermes plugin entry point — shim for src-layout compatibility.

Hermes treats the plugin directory as a flat Python package and looks for
``register(ctx)`` in this file. The actual implementation lives under
``src/meeting_intelligence/plugin/``. This shim adds ``src/`` to ``sys.path``
and re-exports ``register`` so the src-layout package is importable.

See: docs/adr/009-agent-plugins-conformance.md
"""
import sys
from pathlib import Path

_src = str(Path(__file__).parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from meeting_intelligence.plugin import register  # noqa: E402,F401
