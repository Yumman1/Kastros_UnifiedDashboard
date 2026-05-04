"""
WhatsApp webhook receiver with Ollama-powered market data extraction.
Receives Evolution API webhooks, extracts text, uses Ollama to parse commodity prices,
and inserts normalized data into market_data for the Live Rates page.
"""

import json
import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify

# Ensure agri_dashboard is importable
_script_dir = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_script_dir)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

try:
    from extractor import process_message_to_db_format
except ImportError:
    from agri_dashboard.extractor import process_message_to_db_format

app = Flask(__name__)
WEBHOOK_LOG_FULL_PAYLOAD = os.getenv("WEBHOOK_LOG_FULL_PAYLOAD", "false").lower() in ("1", "true", "yes")
WEBHOOK_LOG_MAX_CHARS = int(os.getenv("WEBHOOK_LOG_MAX_CHARS", "6000"))
WEBHOOK_IGNORE_FROM_ME = os.getenv("WEBHOOK_IGNORE_FROM_ME", "true").lower() in ("1", "true", "yes")
WEBHOOK_GROUPS_ONLY = os.getenv("WEBHOOK_GROUPS_ONLY", "true").lower() in ("1", "true", "yes")


def extract_message_text_from_evolution(payload: dict) -> str | None:
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


# Cache JID -> group name for webhook (avoids repeated API calls)
_jid_to_name_cache = {}
_jid_cache_fetched_at = 0
_JID_CACHE_TTL = 300  # refresh every 5 min


def _resolve_jid_to_name(jid: str) -> str:
    """Resolve JID to group/chat name via Evolution API. Uses cache."""
    global _jid_to_name_cache, _jid_cache_fetched_at
    import time
    now = time.time()
    if jid in _jid_to_name_cache:
        return _jid_to_name_cache[jid]
    if now - _jid_cache_fetched_at > _JID_CACHE_TTL or not _jid_to_name_cache:
        try:
            from agri_dashboard.evolution_api import find_chats, EVOLUTION_INSTANCE
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
    """Extract source (group/chat name preferred over JID) and timestamp from Evolution payload."""
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
    # Timestamp: messageTimestamp (epoch seconds)
    ts = data.get("messageTimestamp")
    if ts is not None:
        try:
            timestamp = datetime.fromtimestamp(int(ts))
        except (ValueError, TypeError):
            pass
    return source, timestamp


def _get_db():
    """Lazy import to avoid circular deps and ensure DB is in correct dir."""
    from agri_dashboard.database import init_db, insert_market_data
    init_db()
    return insert_market_data


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Evolution API webhook. Extracts text, runs LLM extraction, inserts into market_data.
    """
    try:
        payload = request.get_json(force=True, silent=True)
    except Exception:
        payload = None

    if not payload:
        try:
            payload = request.get_json(force=False)
        except Exception:
            payload = None

    if not payload:
        return jsonify({"ok": False, "error": "invalid_json"}), 400

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
        return jsonify({"ok": True, "message": "ignored_from_me", "records_inserted": 0}), 200

    if WEBHOOK_GROUPS_ONLY and remote_jid and not remote_jid.endswith("@g.us"):
        return jsonify({"ok": True, "message": "ignored_non_group", "records_inserted": 0}), 200

    text = extract_message_text_from_evolution(payload)
    if not text:
        print("[webhook] No text message in payload")
        return jsonify({"ok": True, "message": "no_text", "records_inserted": 0}), 200

    source, timestamp = extract_source_and_timestamp_from_evolution(payload)

    # Preserve exact raw text before LLM extraction (for accurate storage and inspection)
    raw_text = text.strip() if text else ""
    extracted_trades = process_message_to_db_format(raw_text, message_timestamp=timestamp)

    if not extracted_trades:
        print("[webhook] No valid trades found in message:", repr(raw_text)[:120])
        return jsonify({"ok": True, "text": raw_text[:200], "records_inserted": 0, "result": []}), 200

    insert_market_data = _get_db()
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
                raw_message=raw_text,  # Store full raw text (no truncation) for Data Inspector
            )
            count += 1
        except Exception as e:
            print(f"[webhook] insert error: {e}")

    print("[webhook] Raw text (length=%d):" % len(raw_text), repr(raw_text)[:100])
    print("[webhook] Extracted (standardized):", json.dumps(extracted_trades, indent=2))
    print(f"[webhook] Inserted {count} records")

    records = extracted_trades

    return jsonify({
        "ok": True,
        "text": raw_text[:200],
        "result": records,
        "records_inserted": count,
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
