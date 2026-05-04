"""
ASGI entry for Vercel (same layout as vercel.com/examples/fastapi).
Exposes a top-level name `app` that is the FastAPI instance.
"""

from __future__ import annotations

import sys
from pathlib import Path

_agri = Path(__file__).resolve().parent.parent / "agri_dashboard"
_agri_str = str(_agri)
if _agri_str not in sys.path:
    sys.path.insert(0, _agri_str)

from api import app  # noqa: E402  # agri_dashboard/api.py
