"""
Vercel ASGI entry — MUST live at repo root (not in /app).

Do not use a top-level Python package named `app/`; Vercel may mis-detect Next.js
App Router and never run this FastAPI app (edge 403/404).
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

_REPO_ROOT = Path(__file__).resolve().parent
_agri = _REPO_ROOT / "agri_dashboard"
_agri_str = str(_agri)
if _agri_str not in sys.path:
    sys.path.insert(0, _agri_str)

_log.info(
    "boot start cwd=%s agri_dashboard=%s VERCEL=%s VERCEL_ENV=%s GIT=%s",
    os.getcwd(),
    _agri_str,
    os.environ.get("VERCEL"),
    os.environ.get("VERCEL_ENV"),
    os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:12],
)

try:
    from api import app  # noqa: E402
    _log.info("boot ok: imported api.app title=%r", getattr(app, "title", ""))
except Exception:  # pragma: no cover - production diagnostics
    _log.exception("boot FAILED importing agri_dashboard.api — serving debug app only")
    tb = traceback.format_exc()
    from fastapi import FastAPI, Request

    app = FastAPI(title="Kastros Unified (import failed)", version="0.0.0", redirect_slashes=False)

    @app.get("/")
    def _import_error_root():
        return {
            "ok": False,
            "stage": "import_agri_dashboard.api",
            "message": "See traceback and Vercel Runtime Logs lines tagged [kastros]",
            "traceback": tb[-12000:],
        }

    @app.get("/{full_path:path}")
    def _import_error_catch(request: Request, full_path: str):
        return {
            "ok": False,
            "stage": "import_agri_dashboard.api",
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
    sha = os.environ.get("VERCEL_GIT_COMMIT_SHA") or "local"
    response.headers["X-Kastros-Git"] = sha[:12] if len(sha) > 12 else sha
    return response
