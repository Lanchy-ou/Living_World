"""Make the shared test builders in ``tests/unit`` importable from every test folder."""

from __future__ import annotations

import sys
from pathlib import Path

_UNIT = str(Path(__file__).resolve().parent / "unit")
if _UNIT not in sys.path:
    sys.path.insert(0, _UNIT)
