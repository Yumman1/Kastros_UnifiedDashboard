"""
Vercel ASGI entry when Project Root Directory is `agri_dashboard`.

Keeps FastAPI discoverable as main.py without colliding with Streamlit (streamlit_app.py).
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [kastros] %(message)s",
    stream=sys.stderr,
    force=True,
)
_log = logging.getLogger("kastros.boot")

_agri = Path(__file__).resolve().parent
_agri_str = str(_agri)
if _agri_str not in sys.path:
    sys.path.insert(0, _agri_str)

_log.info(
    "boot (agri_dashboard root) cwd=%s agri_dashboard=%s VERCEL=%s VERCEL_ENV=%s GIT=%s",
    os.getcwd(),
    _agri_str,
    os.environ.get("VERCEL"),
    os.environ.get("VERCEL_ENV"),
    os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:12],
)

try:
    from api import app  # noqa: E402
    _log.info("boot ok: imported api.app title=%r", getattr(app, "title", ""))
except Exception:  # pragma: no cover
    _log.exception("boot FAILED importing api — serving debug app only")
    tb = traceback.format_exc()
    from fastapi import FastAPI, Request

    app = FastAPI(title="Kastros Unified (import failed)", version="0.0.0", redirect_slashes=False)

    @app.get("/")
    def _import_error_root():
        return {
            "ok": False,
            "stage": "import api (agri_dashboard)",
            "message": "See traceback and Runtime Logs [kastros]",
            "traceback": tb[-12000:],
        }

    @app.get("/{full_path:path}")
    def _import_error_catch(request: Request, full_path: str):
        return {
            "ok": False,
            "stage": "import api (agri_dashboard)",
            "path": request.url.path,
            "traceback": tb[-12000:],
        }


@app.middleware("http")
async def _request_log_middleware(request, call_next):  # type: ignore[no-untyped-def]
    p = request.url.path
    _log.info("HTTP %s %s", request.method, p)
    try:
        response = await call_next(request)
    except Exception:
        _log.exception("HTTP %s %s handler crashed", request.method, p)
        raise
    sc = getattr(response, "status_code", "?")
    _log.info("HTTP %s %s -> %s", request.method, p, sc)
    response.headers["X-Kastros-Handler"] = "fastapi"
    response.headers["X-Kastros-Path"] = p
    response.headers["X-Kastros-Entry"] = "agri_dashboard/main.py"
    sha = os.environ.get("VERCEL_GIT_COMMIT_SHA") or "local"
    response.headers["X-Kastros-Git"] = sha[:12] if len(sha) > 12 else sha
    return response
