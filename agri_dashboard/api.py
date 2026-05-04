"""
FastAPI backend for the Commodities Trading Dashboard.
Decoupled API service handling webhook, ingest, and rates.
"""

import json
import os
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

_app_dir = os.path.dirname(os.path.abspath(__file__))
import sys
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
from dotenv import load_dotenv
load_dotenv(os.path.join(_app_dir, ".env"))
WEBHOOK_LOG_FULL_PAYLOAD = os.getenv("WEBHOOK_LOG_FULL_PAYLOAD", "false").lower() in ("1", "true", "yes")
WEBHOOK_LOG_MAX_CHARS = int(os.getenv("WEBHOOK_LOG_MAX_CHARS", "6000"))
WEBHOOK_IGNORE_FROM_ME = os.getenv("WEBHOOK_IGNORE_FROM_ME", "true").lower() in ("1", "true", "yes")
WEBHOOK_GROUPS_ONLY = os.getenv("WEBHOOK_GROUPS_ONLY", "true").lower() in ("1", "true", "yes")

# Import after path setup (agri_dashboard in path for sibling imports)
from database import (
    init_db,
    insert_market_data,
    get_todays_prices,
    get_recent_prices,
    get_historic_data,
    get_recent_entries_for_inspector,
)
from ingest_whatsapp import (
    fetch_whatsapp_messages,
    process_messages,
    record_last_ingest,
    get_last_ingest,
    ingest_from_export,
    EVOLUTION_API_KEY,
)
from extractor import process_message_to_db_format, process_message_with_debug
from whatsapp_parser import parse_whatsapp_export
from evolution_api import find_chats, EVOLUTION_INSTANCE
from analysis import get_latest_arbitrage_opportunities, get_arbitrage_summary
from news_engine import get_market_news, get_sentiment_summary

app = FastAPI(
    title="Pakistan Commodities Trading API",
    description="Backend API for WhatsApp data ingestion and market rates",
    version="1.0.0",
    # Vercel's edge + Starlette slash redirects often disagree; avoid redirect loops.
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # allow_credentials=True is invalid with origin "*" (Starlette/FastAPI); breaks CORS for some clients.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Webhook payload extraction (Evolution API format) ---

def extract_message_text_from_evolution(payload: dict) -> Optional[str]:
    """Extract text from Evolution webhook: conversation, extendedTextMessage.text, or imageMessage.caption"""
    if not payload or not isinstance(payload, dict):
        return None
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return None
    message = data.get("message")
    if not message or not isinstance(message, dict):
        return None
    text = message.get("conversation")
    if isinstance(text, str) and text.strip():
        return text.strip()
    ext = message.get("extendedTextMessage", {}) or {}
    if isinstance(ext, dict):
        text = ext.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    img = message.get("imageMessage", {}) or {}
    if isinstance(img, dict):
        text = img.get("caption")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


_jid_to_name_cache: dict = {}
_jid_cache_fetched_at = 0.0
_JID_CACHE_TTL = 300


def _resolve_jid_to_name(jid: str) -> str:
    """Resolve JID to group/chat name via Evolution API. Uses cache."""
    global _jid_to_name_cache, _jid_cache_fetched_at
    import time
    now = time.time()
    if jid in _jid_to_name_cache:
        return _jid_to_name_cache[jid]
    if now - _jid_cache_fetched_at > _JID_CACHE_TTL or not _jid_to_name_cache:
        try:
            chats = find_chats(EVOLUTION_INSTANCE)
            for c in chats:
                j = c.get("remoteJid") or c.get("id") or c.get("jid")
                name = c.get("name") or c.get("subject") or c.get("pushName")
                if j and name:
                    _jid_to_name_cache[str(j)] = str(name).strip()
            _jid_cache_fetched_at = now
        except Exception:
            pass
    return _jid_to_name_cache.get(jid, jid)


def extract_source_and_timestamp_from_evolution(payload: dict) -> tuple[str, datetime]:
    """Extract source (group/chat name) and timestamp from Evolution payload."""
    source = "WhatsApp"
    timestamp = datetime.now()
    if not payload or not isinstance(payload, dict):
        return source, timestamp
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return source, timestamp
    key = data.get("key", {}) or {}
    jid = None
    if isinstance(key, dict):
        jid = key.get("remoteJid") or key.get("keyRemoteJid")
    if jid:
        source = _resolve_jid_to_name(str(jid))
    if not source or source == "WhatsApp":
        source = data.get("pushName") or "WhatsApp"
    ts = data.get("messageTimestamp")
    if ts is not None:
        try:
            timestamp = datetime.fromtimestamp(int(ts))
        except (ValueError, TypeError):
            pass
    return source, timestamp


# --- Request/Response models ---

class IngestExportRequest(BaseModel):
    """Request body for ingest from export."""
    content: str
    group_name: str = "WhatsApp Export"


# --- Endpoints ---


@app.get("/")
def read_root():
    """Landing page for Vercel / root URL (avoids 404 on bare deployment)."""
    return {
        "service": "Pakistan Commodities Trading API",
        "docs": "/docs",
        "health": "/health",
        "note": "Streamlit UI is streamlit_app.py (not on Vercel); use Streamlit Cloud or run locally.",
    }


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_db()


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(payload: dict):
    """
    Evolution API webhook. Receives WhatsApp messages, extracts commodity prices
    using Gemini, and inserts into market_data.
    """
    # Log payload safely (full dump optional via WEBHOOK_LOG_FULL_PAYLOAD=true)
    try:
        raw_json = json.dumps(payload, ensure_ascii=False)
        if WEBHOOK_LOG_FULL_PAYLOAD or len(raw_json) <= WEBHOOK_LOG_MAX_CHARS:
            print("[webhook] RAW JSON PAYLOAD:\n" + raw_json)
        else:
            print(
                "[webhook] RAW JSON PAYLOAD (truncated):\n"
                + raw_json[:WEBHOOK_LOG_MAX_CHARS]
                + f"... <truncated {len(raw_json) - WEBHOOK_LOG_MAX_CHARS} chars>"
            )
    except Exception as e:
        print(f"[webhook] Could not serialize payload: {e}")

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    key = data.get("key", {}) if isinstance(data, dict) else {}
    remote_jid = str(key.get("remoteJid") or "")
    from_me = bool(key.get("fromMe")) if isinstance(key, dict) else False

    if WEBHOOK_IGNORE_FROM_ME and from_me:
        return {"ok": True, "message": "ignored_from_me", "records_inserted": 0}

    if WEBHOOK_GROUPS_ONLY and remote_jid and not remote_jid.endswith("@g.us"):
        return {"ok": True, "message": "ignored_non_group", "records_inserted": 0}

    text = extract_message_text_from_evolution(payload)
    if not text:
        return {"ok": True, "message": "no_text", "records_inserted": 0}

    # Preserve exact raw text before LLM extraction
    raw_text = text.strip()

    source, timestamp = extract_source_and_timestamp_from_evolution(payload)
    records, debug_entries = process_message_with_debug(raw_text, message_timestamp=timestamp)
    extracted_trades = [{"commodity": r.get("commodity") or r.get("category"), "price": r["price"], "city": r["city"]} for r in records]

    try:
        from debug_log import append_log
        for de in debug_entries:
            go = de.get("gemini_output") or ""
            ge = None if (go and not ("Error" in go or "429" in go or go.startswith("("))) else go
            append_log(
                raw_message=de.get("line", raw_text)[:2000],
                source=source,
                gemini_output=None if ge else go,
                gemini_error=ge,
                records_extracted=len(de.get("extracted", [])),
                records_json=json.dumps(de.get("extracted", [])) if de.get("extracted") else None,
            )
    except Exception:
        pass

    if not extracted_trades:
        return {"ok": True, "text": raw_text[:200], "records_inserted": 0, "result": []}

    count = 0
    for trade in extracted_trades:
        try:
            insert_market_data(
                timestamp=timestamp,
                commodity=trade["commodity"],
                source=source,
                price=trade["price"],
                city=trade["city"],
                sentiment_score=0.0,
                raw_message=raw_text,  # Full raw text for Data Inspector
            )
            count += 1
        except Exception as e:
            print(f"[webhook] insert error: {e}")

    return {
        "ok": True,
        "text": raw_text[:200],
        "result": extracted_trades,
        "records_inserted": count,
    }


@app.post("/ingest")
async def ingest(use_mock: bool = False):
    """
    Run extraction logic: fetch messages from Evolution API, extract commodity
    prices via Gemini, and store in database.
    """
    debug_lines: list[str] = []
    try:
        init_db()
        messages = fetch_whatsapp_messages(debug_out=debug_lines)
    except Exception as e:
        debug_lines.append(f"[ingest] Fetch error: {type(e).__name__}: {e}")
        return {
            "ok": False,
            "count": 0,
            "source": "evolution" if EVOLUTION_API_KEY else "api",
            "messages_fetched": None,
            "debug": debug_lines,
            "error": str(e),
        }

    if messages is None:
        record_last_ingest(0, "evolution" if EVOLUTION_API_KEY else "api")
        return {
            "ok": True,
            "count": 0,
            "source": "evolution" if EVOLUTION_API_KEY else "api",
            "messages_fetched": None,
            "debug": debug_lines,
        }

    if len(messages) == 0:
        record_last_ingest(0, "evolution" if EVOLUTION_API_KEY else "api")
        return {
            "ok": True,
            "count": 0,
            "source": "evolution" if EVOLUTION_API_KEY else "api",
            "messages_fetched": 0,
            "debug": debug_lines,
        }

    total_fetched = len(messages)
    if use_mock:
        from ingest_whatsapp import generate_mock_data
        messages = generate_mock_data()

    try:
        count = process_messages(messages, use_message_timestamp=True, debug_out=debug_lines)
    except Exception as e:
        debug_lines.append(f"[ingest] Process error: {type(e).__name__}: {e}")
        import traceback
        debug_lines.append(traceback.format_exc())
        return {
            "ok": False,
            "count": 0,
            "source": "evolution" if EVOLUTION_API_KEY else "api",
            "messages_fetched": total_fetched,
            "debug": debug_lines,
            "error": str(e),
        }

    source = "evolution" if EVOLUTION_API_KEY else "api"
    record_last_ingest(count, source)
    return {
        "ok": True,
        "count": count,
        "source": source,
        "messages_fetched": total_fetched,
        "debug": debug_lines,
    }


@app.post("/ingest/export")
async def ingest_from_file(request: IngestExportRequest):
    """
    Ingest from WhatsApp chat export text. Parses and extracts commodity prices.
    """
    init_db()
    parsed = parse_whatsapp_export(
        request.content,
        group_name=request.group_name or "WhatsApp Export"
    )
    if not parsed:
        return {
            "ok": False,
            "count": 0,
            "message": "No messages could be parsed from the export.",
        }
    count = ingest_from_export(parsed, group_name=request.group_name or "WhatsApp Export")
    return {"ok": True, "count": count}


@app.get("/rates")
def get_rates(
    days: int = Query(30, ge=1, le=365, description="Number of days of data"),
    commodity: Optional[str] = Query(None, description="Filter by commodity"),
    city: Optional[str] = Query(None, description="Filter by city"),
):
    """
    Serve market rates to the frontend. Returns recent prices with optional filters.
    """
    data = get_recent_prices(days=days)
    if not data:
        return {"data": [], "count": 0}

    # Convert to list of dicts for JSON
    columns = ["timestamp", "commodity", "source", "price", "city", "sentiment_score", "raw_message"]
    rows = []
    for row in data:
        d = dict(zip(columns, row))
        if commodity and d.get("commodity") != commodity:
            continue
        if city and d.get("city") != city:
            continue
        d["timestamp"] = d["timestamp"].isoformat() if hasattr(d["timestamp"], "isoformat") else str(d["timestamp"])
        rows.append(d)

    return {"data": rows, "count": len(rows)}


@app.get("/inspector")
def get_inspector_data(limit: int = Query(50, ge=1, le=200)):
    """
    Return most recent market_data entries for Data Inspector tab.
    Includes raw_message and parsed fields (commodity, price, city) for side-by-side comparison.
    """
    entries = get_recent_entries_for_inspector(limit=limit)
    for e in entries:
        if "timestamp" in e and hasattr(e["timestamp"], "isoformat"):
            e["timestamp"] = e["timestamp"].isoformat()
    return {"ok": True, "entries": entries}


@app.get("/rates/last-ingest")
def last_ingest():
    """Return last ingest metadata."""
    info = get_last_ingest()
    return {"last_ingest": info} if info else {"last_ingest": None}


@app.get("/debug")
def get_debug_log(limit: int = Query(50, ge=1, le=200)):
    """Return recent extraction debug entries: raw message, Gemini output, source."""
    try:
        from debug_log import get_recent_logs
        return {"ok": True, "entries": get_recent_logs(limit=limit)}
    except Exception as e:
        return {"ok": False, "entries": [], "error": str(e)}


@app.post("/seed")
def seed():
    """Seed sample data for testing."""
    from database import seed_data
    seed_data()
    return {"ok": True, "message": "Sample data seeded"}


@app.get("/forecast")
def get_forecast(
    commodity: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    periods: int = Query(7, ge=1, le=30),
):
    """Get AI-powered price forecast."""
    from forecast import get_forecast_with_history

    historical_df, forecast_df = get_forecast_with_history(
        commodity=commodity,
        city=city,
        periods=periods,
    )
    if forecast_df is None or historical_df is None:
        return {"ok": False, "historical": None, "forecast": None}
    return {
        "ok": True,
        "historical": historical_df.to_dict(orient="records"),
        "forecast": forecast_df.to_dict(orient="records"),
    }


@app.get("/arbitrage")
def get_arbitrage(
    min_profit_margin: float = Query(0.05, ge=0, le=1),
):
    """Get arbitrage opportunities between cities."""
    opportunities_df = get_latest_arbitrage_opportunities(min_profit_margin=min_profit_margin)
    summary = get_arbitrage_summary()
    if opportunities_df.empty:
        return {"ok": True, "opportunities": [], "summary": summary}
    opportunities_df["date"] = opportunities_df["date"].astype(str)
    return {
        "ok": True,
        "opportunities": opportunities_df.to_dict(orient="records"),
        "summary": summary,
    }


@app.get("/news")
def get_news(
    num_headlines: int = Query(10, ge=1, le=50),
):
    """Get market news and sentiment."""
    news_items = get_market_news(num_headlines=num_headlines)
    sentiment_summary = get_sentiment_summary()
    return {
        "ok": True,
        "news": news_items,
        "sentiment_summary": sentiment_summary,
    }


@app.get("/historic")
def get_historic(
    commodity: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
):
    """Get historic market data for trends."""
    data = get_historic_data(commodity=commodity, city=city)
    if not data:
        return {"data": [], "count": 0}
    columns = ["timestamp", "commodity", "source", "price", "city", "sentiment_score"]
    rows = []
    for row in data:
        d = dict(zip(columns, row))
        d["timestamp"] = d["timestamp"].isoformat() if hasattr(d["timestamp"], "isoformat") else str(d["timestamp"])
        rows.append(d)
    return {"data": rows, "count": len(rows)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
