"""
Vercel FastAPI entry when Root Directory is `agri_dashboard` (same ASGI as main.py).
"""

from main import app  # noqa: E402 — agri_dashboard/main.py

__all__ = ["app"]
