"""
ASGI entry for Vercel. Exposes `app` for the Python runtime.

If `agri_dashboard.api` fails to import (missing deps, bad env), we still expose a
small FastAPI app that returns the traceback so Runtime Logs + HTTP show why.
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

_agri = Path(__file__).resolve().parent.parent / "agri_dashboard"
_agri_str = str(_agri)
if _agri_str not in sys.path:
    sys.path.insert(0, _agri_str)

_log.info(
    "boot start cwd=%s agri_dashboard=%s VERCEL=%s UV=%s",
    os.getcwd(),
    _agri_str,
    os.environ.get("VERCEL"),
    os.environ.get("VERCEL_ENV"),
)

try:
    from api import app  # noqa: E402
    _log.info("boot ok: imported api.app title=%r", getattr(app, "title", ""))
except Exception:  # pragma: no cover - production diagnostics
    _log.exception("boot FAILED importing agri_dashboard.api — serving debug app only")
    tb = traceback.format_exc()
    from fastapi import FastAPI, Request

    app = FastAPI(title="Kastros Unified (import failed)", version="0.0.0")

    @app.get("/")
    def _import_error_root():
        return {
            "ok": False,
            "stage": "import_agri_dashboard.api",
            "message": "See `traceback` and Vercel Runtime Logs for [kastros]",
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
    _log.info("HTTP %s %s -> %s", request.method, p, getattr(response, "status_code", "?"))
    return response
