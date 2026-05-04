"""
Offline cotton-only Gemini test runner for WhatsApp export files.

This script avoids API fetching and processes only a small subset of messages
to protect Gemini quota while validating extraction quality.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from whatsapp_parser import parse_whatsapp_export
from dictionaries import CITY_MAP, COMMODITY_GROUPS
from database import init_db, insert_market_data


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHAT_PATH = PROJECT_ROOT / "WhatsApp Chat with Business Club Commodities.txt"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

COTTON_KEYWORDS = {
    kw.lower() for kw in COMMODITY_GROUPS.get("COTTON", [])
}.union({"cf", "cf 200b", "cotton", "kapas", "phutti", "کپاس"})
PRICE_HINT_KEYWORDS = {"rs", "pkr", "rate", "price", "maund", "40kg", "kg", "cf"}
FUTURES_HINTS = {"ice", "nyce", "dec", "mar", "may", "cents/lb", "points", "index", "awp"}


def _load_env() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env")


def _looks_cotton_related(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in COTTON_KEYWORDS)


def _looks_priced_message(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in PRICE_HINT_KEYWORDS) and bool(re.search(r"\d", t))


def _is_probable_futures(text: str) -> bool:
    t = (text or "").lower()
    return any(h in t for h in FUTURES_HINTS)


def _select_candidate_messages(parsed_messages: List[Dict[str, Any]], max_messages: int) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for msg in parsed_messages:
        text = msg.get("message", "")
        if not text or len(text.strip()) < 8:
            continue
        if not _looks_cotton_related(text):
            continue
        if not _looks_priced_message(text):
            continue
        candidates.append(msg)
    # Prefer most recent messages for current-market validation
    return candidates[-max_messages:]


def _get_city_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for key, value in CITY_MAP.items():
        lookup[key.lower()] = value
        lookup[value.lower()] = value
    return lookup


CITY_LOOKUP = _get_city_lookup()


def _normalize_city(raw_city: Optional[str], message_text: str) -> str:
    if raw_city:
        c = raw_city.strip().lower()
        if c in CITY_LOOKUP:
            return CITY_LOOKUP[c]
        if c:
            return c.title()

    text = (message_text or "").lower()
    # Prefer longer matches first (e.g., "dg khan" before "khan")
    for key in sorted(CITY_LOOKUP.keys(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", text):
            return CITY_LOOKUP[key]
    return "Unknown"


def _normalize_unit(raw_unit: Optional[str], price_value: float, context_text: str) -> Tuple[Optional[str], Optional[float], str]:
    """
    Return (normalized_unit, price_per_kg, note).
    normalized_unit values: 'kg', 'maund_40kg', or None.
    """
    context = (context_text or "").lower()
    unit = (raw_unit or "").strip().lower()

    if _is_probable_futures(context):
        return None, None, "Skipped futures/international quote"

    # Explicit unit first
    if "kg" in unit or "per kg" in context or "/kg" in context:
        return "kg", float(price_value), "Unit detected as kg"
    if (
        "maund" in unit
        or "mound" in unit
        or "40kg" in unit
        or "40 kg" in unit
        or "maund" in context
        or "40kg" in context
        or "40 kg" in context
    ):
        return "maund_40kg", float(price_value) / 40.0, "Unit detected as maund/40kg"

    # Heuristic fallback based on plausible Pakistan cotton pricing
    # Typical local spot quotes ~ 14,000-18,000 per 40kg -> 350-450 per kg.
    if 2000 <= price_value <= 50000:
        return "maund_40kg", float(price_value) / 40.0, "Heuristic: high value treated as maund/40kg"
    if 40 <= price_value <= 1500:
        return "kg", float(price_value), "Heuristic: value treated as kg"

    return None, None, "Could not infer unit confidently"


def _parse_gemini_json(text: str) -> Dict[str, Any]:
    content = (text or "").strip()
    if not content:
        return {"trades": []}
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if code_block:
        content = code_block.group(1).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"trades": [], "error": "invalid_json", "raw": content[:1000]}


def _call_gemini_for_cotton(
    message_text: str,
    model_name: str,
    message_timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    try:
        from google import genai
    except ImportError as e:
        raise RuntimeError("google-genai is not installed. Run: pip install google-genai") from e

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set in environment/.env")

    system_prompt = (
        "You are an extraction engine for Pakistan cotton market data. "
        "Extract ONLY local cotton spot trade quotes from the given message. "
        "Ignore futures/index/global market summaries (e.g., ICE, Dec'25, points, cents/lb). "
        "When the message date is provided, use it in your reasoning: interpret relative phrases "
        "(e.g. 'today\\'s rate'), seasonal context (cotton harvest Oct–Dec in Pakistan), and include "
        "the date in each trade when available.\n"
        "Return strict JSON only in this schema:\n"
        "{\n"
        '  "trades": [\n'
        "    {\n"
        '      "raw_commodity": "string",\n'
        '      "price_value": number,\n'
        '      "quoted_unit": "kg|maund_40kg|unknown",\n'
        '      "city": "string or Unknown",\n'
        '      "date": "string (YYYY-MM-DD when message date provided, else null)",\n'
        '      "snippet": "short exact line from message",\n'
        '      "confidence": number\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "If no valid local cotton trade exists, return {\"trades\": []}."
    )

    user_content = f"Message:\n{message_text}"
    if message_timestamp is not None:
        date_str = message_timestamp.strftime("%Y-%m-%d")
        user_content += f"\nMessage date (use in your reasoning and include in date field): {date_str}"

    # Follow Google SDK default flow: pick API key from GEMINI_API_KEY environment variable.
    client = genai.Client()
    response = client.models.generate_content(
        model=model_name,
        contents=user_content,
        config={
            "system_instruction": system_prompt,
            "temperature": 0.0,
            "max_output_tokens": 512,
        },
    )
    return _parse_gemini_json(response.text or "")


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _write_outputs(rows: List[Dict[str, Any]]) -> Tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUTPUT_DIR / f"cotton_llm_test_{stamp}.json"
    csv_path = OUTPUT_DIR / f"cotton_llm_test_{stamp}.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    fieldnames = [
        "timestamp",
        "sender",
        "source",
        "message",
        "raw_commodity",
        "commodity",
        "raw_city",
        "city",
        "original_price",
        "detected_unit",
        "price_per_kg_pkr",
        "confidence",
        "status",
        "note",
        "snippet",
        "raw_message_excerpt",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    return json_path, csv_path


def _insert_rows_to_db(rows: List[Dict[str, Any]]) -> int:
    init_db()
    inserted = 0
    for row in rows:
        if row.get("status") != "accepted":
            continue
        price_per_kg = row.get("price_per_kg_pkr")
        if price_per_kg is None:
            continue
        insert_market_data(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            commodity="COTTON",
            source=row.get("source", "Offline Chat Test"),
            price=float(price_per_kg),
            city=row.get("city", "Unknown"),
            sentiment_score=0.0,
            raw_message=row.get("raw_message_excerpt", ""),
        )
        inserted += 1
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run cotton-only Gemini extraction on local WhatsApp export (offline test mode)."
    )
    parser.add_argument(
        "--file",
        type=str,
        default=str(DEFAULT_CHAT_PATH),
        help="Absolute/relative path to WhatsApp export text file.",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=3,
        choices=range(1, 11),
        metavar="[1-10]",
        help="Maximum cotton candidate messages to send to Gemini (default: 3).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        help="Gemini model name (default from GEMINI_MODEL or gemini-2.5-flash).",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Also insert accepted cotton per-kg rows into market_data.db.",
    )
    args = parser.parse_args()

    _load_env()
    chat_path = Path(args.file).resolve()
    if not chat_path.exists():
        raise FileNotFoundError(f"Chat file not found: {chat_path}")

    print(f"[cotton-test] Reading chat export: {chat_path}")
    content = chat_path.read_text(encoding="utf-8", errors="replace")
    parsed_messages = parse_whatsapp_export(content, group_name="Business Club Commodities")
    print(f"[cotton-test] Parsed messages: {len(parsed_messages)}")

    selected = _select_candidate_messages(parsed_messages, args.max_messages)
    print(f"[cotton-test] Cotton candidate messages selected for Gemini: {len(selected)}")
    if not selected:
        print("[cotton-test] No cotton candidates found. Exiting.")
        return

    rows: List[Dict[str, Any]] = []
    for idx, msg in enumerate(selected, start=1):
        message_text = msg.get("message", "")
        sender = msg.get("sender", "Unknown")
        ts = msg.get("timestamp")
        timestamp_iso = ts.isoformat() if isinstance(ts, datetime) else datetime.now().isoformat()

        print(f"[cotton-test] ({idx}/{len(selected)}) Sending message to Gemini...")
        gemini_result = _call_gemini_for_cotton(
            message_text, args.model, message_timestamp=ts if isinstance(ts, datetime) else None
        )
        trades = gemini_result.get("trades", []) if isinstance(gemini_result, dict) else []

        if not trades:
            rows.append(
                {
                    "timestamp": timestamp_iso,
                    "sender": sender,
                    "source": msg.get("source", "WhatsApp Export"),
                    "message": message_text,
                    "raw_commodity": "",
                    "commodity": "",
                    "raw_city": "",
                    "city": "Unknown",
                    "original_price": None,
                    "detected_unit": "",
                    "price_per_kg_pkr": None,
                    "confidence": 0.0,
                    "status": "rejected",
                    "note": "No valid cotton trade extracted by Gemini",
                    "snippet": "",
                    "raw_message_excerpt": message_text[:500],
                }
            )
            continue

        for trade in trades:
            raw_commodity = str(trade.get("raw_commodity", "")).strip()
            if raw_commodity and not _looks_cotton_related(raw_commodity) and not _looks_cotton_related(message_text):
                continue

            original_price = _to_float(trade.get("price_value"))
            if original_price is None:
                rows.append(
                    {
                        "timestamp": timestamp_iso,
                        "sender": sender,
                        "source": msg.get("source", "WhatsApp Export"),
                        "message": message_text,
                        "raw_commodity": raw_commodity,
                        "commodity": "COTTON",
                        "raw_city": trade.get("city", ""),
                        "city": _normalize_city(trade.get("city"), message_text),
                        "original_price": None,
                        "detected_unit": "unknown",
                        "price_per_kg_pkr": None,
                        "confidence": _to_float(trade.get("confidence")) or 0.0,
                        "status": "rejected",
                        "note": "Missing or invalid price_value",
                        "snippet": trade.get("snippet", ""),
                        "raw_message_excerpt": message_text[:500],
                    }
                )
                continue

            context = (trade.get("snippet") or "") + "\n" + message_text
            detected_unit, price_per_kg, note = _normalize_unit(
                raw_unit=trade.get("quoted_unit"),
                price_value=original_price,
                context_text=context,
            )
            status = "accepted" if price_per_kg is not None else "rejected"

            rows.append(
                {
                    "timestamp": timestamp_iso,
                    "sender": sender,
                    "source": msg.get("source", "WhatsApp Export"),
                    "message": message_text,
                    "raw_commodity": raw_commodity,
                    "commodity": "COTTON",
                    "raw_city": trade.get("city", ""),
                    "city": _normalize_city(trade.get("city"), message_text),
                    "original_price": original_price,
                    "detected_unit": detected_unit or "unknown",
                    "price_per_kg_pkr": round(price_per_kg, 4) if price_per_kg is not None else None,
                    "confidence": _to_float(trade.get("confidence")) or 0.0,
                    "status": status,
                    "note": note,
                    "snippet": trade.get("snippet", ""),
                    "raw_message_excerpt": message_text[:500],
                }
            )

    json_path, csv_path = _write_outputs(rows)
    accepted = sum(1 for r in rows if r.get("status") == "accepted")
    rejected = len(rows) - accepted
    print(f"[cotton-test] Accepted: {accepted} | Rejected: {rejected}")
    print(f"[cotton-test] JSON output: {json_path}")
    print(f"[cotton-test] CSV output:  {csv_path}")

    if args.write_db:
        inserted = _insert_rows_to_db(rows)
        print(f"[cotton-test] Inserted into DB: {inserted}")


if __name__ == "__main__":
    main()
