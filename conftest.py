"""Root conftest — ensures project-local packages are importable before
tests/conftest.py is loaded.  This file is intentionally minimal; all
fixtures live in tests/conftest.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).parent
for _extra in ("src", "scripts"):
    _p = str(_root / _extra)
    if _p not in sys.path:
        sys.path.insert(0, _p)
