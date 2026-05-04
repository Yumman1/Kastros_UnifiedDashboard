"""
Client for the Commodities Trading Backend API.
Used by the Streamlit frontend when running in decoupled mode.
"""

import os
import requests
from typing import Any, Optional

API_BASE_URL = os.getenv("API_BASE_URL", "").rstrip("/")
TIMEOUT = 120


def _url(path: str) -> str:
    if not API_BASE_URL:
        raise ValueError("API_BASE_URL not set. Run backend with: uvicorn agri_dashboard.api:app --host 0.0.0.0 --port 8000")
    return f"{API_BASE_URL}{path}"


def _get(path: str, params: Optional[dict] = None) -> dict:
    r = requests.get(_url(path), params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _post(path: str, json: Optional[dict] = None) -> dict:
    r = requests.post(_url(path), json=json, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def is_api_mode() -> bool:
    """True when API_BASE_URL is set and backend should be used."""
    return bool(API_BASE_URL)


def health() -> bool:
    """Check if backend is reachable."""
    try:
        _get("/health")
        return True
    except Exception:
        return False


def get_rates(days: int = 30, commodity: Optional[str] = None, city: Optional[str] = None) -> list:
    resp = _get("/rates", params={"days": days, "commodity": commodity, "city": city})
    return resp.get("data", [])


def get_historic(commodity: Optional[str] = None, city: Optional[str] = None) -> list:
    resp = _get("/historic", params={"commodity": commodity, "city": city})
    return resp.get("data", [])


def run_ingest(use_mock: bool = False) -> dict:
    r = requests.post(_url("/ingest"), params={"use_mock": use_mock}, timeout=300)
    try:
        data = r.json() if r.text else {}
    except Exception:
        data = {}
    if not r.ok:
        err = data.get("error") or data.get("detail") or r.reason or str(r.status_code)
        e = RuntimeError(f"Backend error: {err}")
        e.fetch_api_debug = data.get("debug", [])
        raise e
    if data.get("ok") is False and data.get("error"):
        e = RuntimeError(data.get("error", "Unknown error"))
        e.fetch_api_debug = data.get("debug", [])
        raise e
    return data


def ingest_export(content: str, group_name: str = "WhatsApp Export") -> dict:
    return _post("/ingest/export", json={"content": content, "group_name": group_name})


def get_last_ingest() -> Optional[dict]:
    resp = _get("/rates/last-ingest")
    return resp.get("last_ingest")


def seed_data() -> dict:
    return _post("/seed")


def get_forecast(commodity: Optional[str] = None, city: Optional[str] = None, periods: int = 7) -> dict:
    return _get("/forecast", params={"commodity": commodity, "city": city, "periods": periods})


def get_arbitrage(min_profit_margin: float = 0.05) -> dict:
    return _get("/arbitrage", params={"min_profit_margin": min_profit_margin})


def get_news(num_headlines: int = 10) -> dict:
    return _get("/news", params={"num_headlines": num_headlines})


def get_debug_log(limit: int = 50) -> dict:
    return _get("/debug", params={"limit": limit})


def get_inspector_data(limit: int = 50) -> list:
    """Get most recent market_data entries for Data Inspector tab (raw_message + parsed fields)."""
    resp = _get("/inspector", params={"limit": limit})
    return resp.get("entries", []) if resp.get("ok") else []
