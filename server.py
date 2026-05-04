"""
Vercel FastAPI entrypoint when the Git root is this repository.
See https://vercel.com/docs/frameworks/backend/fastapi
"""

from __future__ import annotations

import sys
from pathlib import Path

_agri = Path(__file__).resolve().parent / "agri_dashboard"
sys.path.insert(0, str(_agri))

from api import app  # noqa: E402

__all__ = ["app"]
