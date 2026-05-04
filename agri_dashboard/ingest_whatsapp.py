"""
WhatsApp data ingestion script for the Commodities Trading Dashboard.
Fetches messages from UltraMsg API and extracts commodity price information.
"""

import re
import json
from datetime import datetime
from typing import List, Tuple, Optional

import requests
from database import insert_market_data, init_db
import os
try:
    from extractor import process_message_to_db_format, process_message_with_debug
except ImportError:
    from agri_dashboard.extractor import process_message_to_db_format, process_message_with_debug
from dotenv import load_dotenv

# File to record last automated/scheduled ingest (for dashboard display)
_agri_dir = os.path.dirname(os.path.abspath(__file__))
LAST_INGEST_FILE = os.path.join(_agri_dir, "last_ingest.json")

# Load .env from agri_dashboard so it works when run from project root (e.g. streamlit run agri_dashboard/streamlit_app.py)
load_dotenv(os.path.join(_agri_dir, ".env"))

# Evolution API (primary, free & open-source: https://github.com/EvolutionAPI/evolution-api)
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "agri-dashboard")
# Optional: one or more chat IDs (comma-separated). Leave empty to fetch from all chats.
EVOLUTION_CHAT_JID = os.getenv("EVOLUTION_CHAT_JID", "")

# UltraMsg API (optional fallback)
ULTRAMSG_INSTANCE_ID = os.getenv("ULTRAMSG_INSTANCE_ID", "")
ULTRAMSG_TOKEN = os.getenv("ULTRAMSG_TOKEN", "") or os.getenv("ULTRAMSG_API_KEY", "")
ULTRAMSG_CHAT_ID = os.getenv("ULTRAMSG_CHAT_ID", "")


def extract_price_from_message(message, commodity_keywords):
    """
    Extract price information from a WhatsApp message using regex.
    
    Args:
        message: The raw message text
        commodity_keywords: List of commodity keywords to search for
    
    Returns:
        Tuple of (commodity, price) if found, else (None, None)
    """
    message_lower = message.lower()
    
    # Check for commodity keywords
    commodity = None
    for keyword in commodity_keywords:
        if keyword.lower() in message_lower:
            commodity = keyword
            break
    
    if not commodity:
        return None, None
    
    # Pattern to find prices: numbers near keywords like "Rate", "Price", "Rs", "PKR"
    # Matches patterns like: "Rate: 8500", "Price Rs 9000", "PKR 10000", etc.
    price_patterns = [
        r'(?:rate|price|rs|pkr)[\s:]*([\d,]+\.?\d*)',  # Rate: 8500 or Price Rs 9000
        r'([\d,]+\.?\d*)[\s]*(?:per|maund|kg|40kg)',  # 8500 per maund
        r'rs\.?\s*([\d,]+\.?\d*)',  # Rs. 8500
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                price = float(price_str)
                return commodity, price
            except ValueError:
                continue
    
    return None, None


def extract_city_from_message(message):
    """
    Extract city name from message.
    Common Pakistan cities for commodities trading.
    """
    cities = ["Karachi", "Lahore", "Faisalabad", "Multan", "Hyderabad", 
              "Rawalpindi", "Islamabad", "Peshawar", "Quetta", "Sialkot"]
    
    for city in cities:
        if city.lower() in message.lower():
            return city
    
    return "Unknown"


def fetch_whatsapp_messages(debug_out: Optional[List[str]] = None):
    """
    Fetch messages: prefers Evolution API (free), then UltraMsg, then None.
    Returns list of message dicts with 'body' or 'message', 'from' or 'source', 'timestamp'.
    If debug_out is a list, appends debug lines.
    """
    def _log(msg: str) -> None:
        if debug_out is not None:
            debug_out.append(f"[fetch_whatsapp] {msg}")

    # 1) Evolution API (free, open-source)
    if EVOLUTION_API_KEY:
        _log(f"EVOLUTION_API_KEY set (len={len(EVOLUTION_API_KEY)}) EVOLUTION_INSTANCE={EVOLUTION_INSTANCE!r}")
        try:
            from evolution_api import fetch_all_messages_for_ingest
            jid_raw = (EVOLUTION_CHAT_JID or "").strip()
            _log(f"EVOLUTION_CHAT_JID raw length={len(jid_raw)} first 50 chars={jid_raw[:50]!r}")
            if jid_raw and "," in jid_raw:
                chat_jids = [s.strip() for s in jid_raw.split(",") if s.strip()]
                _log(f"Using chat_jids: count={len(chat_jids)} first={chat_jids[0][:30] if chat_jids else 'n/a'}...")
                msgs = fetch_all_messages_for_ingest(EVOLUTION_INSTANCE, chat_jids=chat_jids, debug_out=debug_out)
            else:
                _log(f"Using chat_jid single: {jid_raw[:50] if jid_raw else 'None'}...")
                msgs = fetch_all_messages_for_ingest(
                    EVOLUTION_INSTANCE,
                    chat_jid=jid_raw or None,
                    debug_out=debug_out,
                )
            _log(f"fetch_all_messages_for_ingest returned {len(msgs) if msgs else 0} messages")
            return msgs if msgs is not None else []
        except Exception as e:
            _log(f"Exception: {type(e).__name__}: {e}")
            raise RuntimeError(f"Evolution API: {e}") from e

    # 2) UltraMsg (optional)
    if ULTRAMSG_TOKEN and ULTRAMSG_INSTANCE_ID:
        base_url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}"
        if ULTRAMSG_CHAT_ID:
            try:
                url = f"{base_url}/chats/messages"
                params = {"token": ULTRAMSG_TOKEN, "chatId": ULTRAMSG_CHAT_ID, "limit": 500}
                response = requests.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
                raw = data if isinstance(data, list) else data.get("messages", data.get("data", []))
                return _normalize_ultramsg_messages(raw)
            except requests.exceptions.RequestException as e:
                print(f"UltraMsg error: {e}")
                return None
        try:
            url = f"{base_url}/messages"
            params = {"token": ULTRAMSG_TOKEN, "page": 1, "limit": 100, "status": "sent", "sort": "desc"}
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            raw = data if isinstance(data, list) else data.get("messages", data.get("data", []))
            return _normalize_ultramsg_messages(raw)
        except requests.exceptions.RequestException as e:
            print(f"UltraMsg error: {e}")
            return None
    return None


def _normalize_ultramsg_messages(raw: list) -> list:
    """Convert UltraMsg API response items to {body, from, timestamp}."""
    out = []
    for item in (raw or []):
        if not isinstance(item, dict):
            continue
        body = item.get("body") or item.get("message") or item.get("text") or ""
        sender = item.get("from") or item.get("sender") or item.get("author") or "Unknown"
        ts = item.get("timestamp") or item.get("date") or item.get("created_at")
        if ts and isinstance(ts, (int, float)):
            try:
                ts = datetime.fromtimestamp(int(ts)).isoformat()
            except (ValueError, OSError):
                ts = datetime.now().isoformat()
        elif not ts:
            ts = datetime.now().isoformat()
        out.append({"body": body, "from": str(sender), "timestamp": ts})
    return out


def generate_mock_data():
    """
    Generate mock WhatsApp messages for testing when API is unavailable.
    Returns a list of mock message dictionaries.
    """
    commodities = ["Cotton", "Wheat", "Corn"]
    cities = ["Karachi", "Lahore", "Faisalabad", "Multan"]
    sources = ["WhatsApp Group 1", "WhatsApp Group 2", "Market Updates"]
    
    mock_messages = []
    for i in range(10):
        commodity = commodities[i % len(commodities)]
        city = cities[i % len(cities)]
        source = sources[i % len(sources)]
        
        if commodity == "Cotton":
            price = 8500 + (i * 200)
        elif commodity == "Wheat":
            price = 3500 + (i * 100)
        else:
            price = 2800 + (i * 80)
        
        message = f"{commodity} rate in {city}: Rs. {price} per maund. Market is stable."
        mock_messages.append({
            "body": message,
            "from": source,
            "timestamp": datetime.now().isoformat()
        })
    
    return mock_messages


# Standard commodity names (stored in DB)
COMMODITY_STANDARD = ["Cotton", "Wheat", "Corn"]
# Aliases and Urdu/variants -> standard name (lowercase for matching)
COMMODITY_ALIASES = {
    "cotton": "Cotton",
    "kapas": "Cotton",
    "wheat": "Wheat",
    "gandum": "Wheat",
    "ganum": "Wheat",
    "corn": "Corn",
    "makai": "Corn",
    "maize": "Corn",
    "مکئی": "Corn",
    "گندم": "Wheat",
    "کپاس": "Cotton",
}
# City aliases (lowercase) -> standard name
CITY_ALIASES = {
    "karachi": "Karachi",
    "lahore": "Lahore",
    "faisalabad": "Faisalabad",
    "multan": "Multan",
    "hyderabad": "Hyderabad",
    "rawalpindi": "Rawalpindi",
    "islamabad": "Islamabad",
    "peshawar": "Peshawar",
    "quetta": "Quetta",
    "sialkot": "Sialkot",
    "milan": "Multan",  # common typo
    "ملاں": "Multan",
    "ملتان": "Multan",
    "کراچی": "Karachi",
    "لاہور": "Lahore",
}

# Plausible price range (PKR per maund/kg) for filtering noise
PRICE_MIN, PRICE_MAX = 500, 500000


def _normalize_commodity(text: str) -> Optional[str]:
    """Map message text to standard commodity if any alias appears. Returns None if no match."""
    t = text.lower().strip()
    for alias, standard in COMMODITY_ALIASES.items():
        if alias in t:
            return standard
    return None


def _normalize_city(text: str) -> str:
    """Extract and normalize city from message."""
    t = text.lower()
    for alias, standard in CITY_ALIASES.items():
        if alias in t:
            return standard
    return "Unknown"


def _extract_price_candidates(text: str) -> List[float]:
    """Extract all number-like price candidates (plausible range). Handles 8500, 8,500, 85.5k etc."""
    candidates = []
    # Numbers with optional comma/decimal: 8500, 8,500, 3500.50
    for m in re.finditer(r"\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\b", text):
        s = m.group(1).replace(",", "")
        try:
            v = float(s)
            if PRICE_MIN <= v <= PRICE_MAX:
                candidates.append(v)
        except ValueError:
            pass
    # Optional: 85.5k, 10k style
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*k\b", text.lower()):
        try:
            v = float(m.group(1)) * 1000
            if PRICE_MIN <= v <= PRICE_MAX:
                candidates.append(v)
        except ValueError:
            pass
    return candidates


def extract_rates_from_message(message: str) -> List[Tuple[str, float, str]]:
    """
    NLP-style extraction: find commodity + price + city from unstructured text.
    Returns list of (commodity, price, city). One message can yield multiple rates (e.g. wheat 3500 cotton 8500).
    """
    if not message or not message.strip():
        return []
    text = message
    text_lower = text.lower()
    city = _normalize_city(text)
    results = []

    # Find which commodities are mentioned
    mentioned = []
    for alias, standard in COMMODITY_ALIASES.items():
        if alias in text_lower:
            mentioned.append(standard)
    # Deduplicate preserving order
    seen = set()
    commodities = []
    for c in mentioned:
        if c not in seen:
            seen.add(c)
            commodities.append(c)

    if not commodities:
        return []

    prices = _extract_price_candidates(text)
    if not prices:
        # Try strict patterns as fallback
        for pat in [
            r"(?:rate|price|rs|pkr)[\s:]*([\d,]+\.?\d*)",
            r"([\d,]+\.?\d*)\s*(?:per|maund|kg|40kg)",
            r"rs\.?\s*([\d,]+\.?\d*)",
        ]:
            m = re.search(pat, text_lower, re.IGNORECASE)
            if m:
                try:
                    p = float(m.group(1).replace(",", ""))
                    if PRICE_MIN <= p <= PRICE_MAX:
                        prices = [p]
                        break
                except ValueError:
                    pass

    if not prices:
        return []

    # If one commodity and one price, one record
    if len(commodities) == 1 and len(prices) >= 1:
        # Prefer price closest to typical (e.g. first, or near keyword)
        price = prices[0]
        results.append((commodities[0], price, city))
        return results

    # Multiple commodities: try to assign prices by proximity (simple: take first N prices for first N commodities)
    for i, comm in enumerate(commodities):
        if i < len(prices):
            results.append((comm, prices[i], city))
        else:
            results.append((comm, prices[-1], city))
    return results


def extract_price_from_message(message, commodity_keywords):
    """
    Legacy: Extract (commodity, price) using keyword + regex. Prefer extract_rates_from_message for new code.
    """
    message_lower = message.lower()
    commodity = None
    for keyword in commodity_keywords:
        if keyword.lower() in message_lower:
            commodity = keyword
            break
    if not commodity:
        return None, None
    price_patterns = [
        r'(?:rate|price|rs|pkr)[\s:]*([\d,]+\.?\d*)',
        r'([\d,]+\.?\d*)[\s]*(?:per|maund|kg|40kg)',
        r'rs\.?\s*([\d,]+\.?\d*)',
    ]
    for pattern in price_patterns:
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                price = float(price_str)
                return commodity, price
            except ValueError:
                continue
    return None, None


COMMODITY_KEYWORDS = ["Cotton", "Wheat", "Corn"]


def _sentiment_from_text(text: str) -> float:
    """Simple sentiment score from keywords."""
    t = text.lower()
    if any(w in t for w in ["up", "rise", "increase", "good"]):
        return 0.5
    if any(w in t for w in ["down", "fall", "decrease", "bad"]):
        return -0.5
    return 0.0


# Fast pre-filter: skip extraction for messages with no commodity/price hints
_COMMODITY_KEYWORDS = frozenset(
    "cotton wheat corn gandum ganum makai maize kapas rate price rs pkr maund 40kg "
    "rice sugar cheeni oil ghee meezan dalda irri sella basmati atta flour"
    .split()
)


def _maybe_has_commodity_price(text: str) -> bool:
    """Quick check: skip LLM if message has no commodity or price hints."""
    if not text or len(text) < 5:
        return False
    t = text.lower()
    if any(kw in t for kw in _COMMODITY_KEYWORDS):
        return True
    if re.search(r"\b\d{3,6}\b", text):
        return True
    return False


def process_messages(messages: list, use_message_timestamp: bool = True, debug_out: Optional[List[str]] = None) -> int:
    """
    Process a list of message dicts into market_data table.
    Uses LLM (Ollama) extraction to get commodity, price, city from unstructured text.
    Each item: body/message, source (group name), timestamp.
    Returns number of records inserted.
    """
    init_db()
    count = 0
    for i, msg in enumerate(messages):
        if isinstance(msg, dict):
            text = msg.get("body", "") or msg.get("message", "") or msg.get("text", "")
            source = msg.get("source", "") or msg.get("from", "Unknown")
            ts = msg.get("timestamp")
        else:
            text, source, ts = str(msg), "Unknown", datetime.now()
        if not text or not text.strip():
            continue
        if not _maybe_has_commodity_price(text):
            continue
        if debug_out and (count == 0 or (i + 1) % 5 == 0):
            debug_out.append(f"[process] Checking message {i+1}/{len(messages)} (candidates so far: {count})")
        if isinstance(ts, datetime):
            timestamp = ts
        elif isinstance(ts, str):
            try:
                timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=None)
            except ValueError:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()
        records, debug_entries = process_message_with_debug(text, message_timestamp=timestamp)
        try:
            from debug_log import append_log
            for de in debug_entries:
                gemini_out = de.get("gemini_output") or ""
                gemini_err = None
                if gemini_out.startswith("(") or "Error" in gemini_out or "429" in gemini_out:
                    gemini_err = gemini_out
                    gemini_out = None
                append_log(
                    raw_message=de.get("line", text)[:500],
                    source=str(source),
                    gemini_output=gemini_out,
                    gemini_error=gemini_err,
                    records_extracted=len(de.get("extracted", [])),
                    records_json=json.dumps(de.get("extracted", [])) if de.get("extracted") else None,
                )
        except Exception:
            pass
        for r in records:
            sentiment_score = _sentiment_from_text(text)
            insert_market_data(
                timestamp=timestamp,
                commodity=r.get("commodity") or r.get("category", ""),
                source=str(source),
                price=r["price"],
                city=r["city"],
                sentiment_score=sentiment_score,
                raw_message=text[:500],
            )
            count += 1
    return count


def ingest_from_export(parsed_messages: list, group_name: str = "WhatsApp Export") -> int:
    """
    Ingest messages from a parsed WhatsApp chat export (from whatsapp_parser).
    parsed_messages: list of dicts with keys timestamp, sender, message, source.
    Returns number of records inserted.
    """
    payload = []
    for p in parsed_messages:
        payload.append({
            "body": p.get("message", ""),
            "from": p.get("sender", "Unknown"),
            "timestamp": p.get("timestamp"),
            "source": p.get("source", group_name)
        })
    return process_messages(payload, use_message_timestamp=True)


def record_last_ingest(count: int, source: str):
    """Write last ingest time/count to file for dashboard display."""
    try:
        with open(LAST_INGEST_FILE, "w") as f:
            json.dump({"at": datetime.now().isoformat(), "count": count, "source": source}, f)
    except Exception:
        pass


def get_last_ingest():
    """Return last ingest info for dashboard: dict with at, count, source or None."""
    if not os.path.isfile(LAST_INGEST_FILE):
        return None
    try:
        with open(LAST_INGEST_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def ingest_data(use_mock_if_no_api: bool = False, debug: bool = True):
    """
    Fetch WhatsApp data from Evolution API (or UltraMsg) and store in database.
    No mock data: if no messages are returned, count is 0. Set use_mock_if_no_api=True only for testing.
    Returns (success: bool, count: int, source: str, messages_fetched: int | None, debug_lines: list).
    messages_fetched is the raw number of messages from API (None if fetch failed).
    debug_lines is a list of debug log lines (when debug=True).
    """
    init_db()
    debug_lines = []
    messages = fetch_whatsapp_messages(debug_out=debug_lines if debug else None)
    if messages is None and use_mock_if_no_api:
        messages = generate_mock_data()
    if messages is None:
        debug_lines.append("[ingest_data] fetch_whatsapp_messages returned None")
        record_last_ingest(0, "evolution" if EVOLUTION_API_KEY else "api")
        return True, 0, "evolution" if EVOLUTION_API_KEY else "api", None, debug_lines
    if len(messages) == 0:
        debug_lines.append(f"[ingest_data] fetch returned 0 messages (list len=0)")
        record_last_ingest(0, "evolution" if EVOLUTION_API_KEY else "api")
        return True, 0, "evolution" if EVOLUTION_API_KEY else "api", 0, debug_lines
    total_fetched = len(messages)
    debug_lines.append(f"[ingest_data] Processing {total_fetched} messages (LLM only for commodity/price candidates)")
    count = process_messages(messages, use_message_timestamp=True, debug_out=debug_lines if debug else None)
    source = "evolution" if EVOLUTION_API_KEY else ("api" if (ULTRAMSG_TOKEN and ULTRAMSG_INSTANCE_ID) else "none")
    record_last_ingest(count, source)
    debug_lines.append(f"[ingest_data] Parsed {count} price records from {total_fetched} messages")
    return True, count, source, total_fetched, debug_lines


if __name__ == "__main__":
    ok, count, source = ingest_data()
    print(f"Data ingestion complete! Processed {count} records (source: {source}).")
