"""
Gemini extraction engine with contextual memory (RAG-lite) and HITL routing.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Dict, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from database import (
    fetch_master_dictionary,
    insert_market_trade,
    insert_pending_trade,
    search_model_memory,
    search_rejected_trades,
)


_APP_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_APP_DIR, ".env"))

MODEL_NAME = "gemini-2.5-flash"
COTTON_MAUND_KG = 37.324


def preprocess_text(text: str) -> str:
    """Apply deterministic slang replacements before AI extraction."""
    cleaned = text or ""
    for row in fetch_master_dictionary():
        slang = str(row["slang_word"] or "").strip()
        standard = str(row["standard_word"] or "").strip()
        if slang:
            cleaned = cleaned.replace(slang, standard)
    return cleaned


def _context_words(text: str) -> list[str]:
    return sorted(set(re.findall(r"[A-Za-z]{4,}", (text or "").lower())))


def get_relevant_memories(text: str) -> str:
    """
    Retrieve related past mistakes from model_memory based on text keywords.
    """
    words = _context_words(text)
    matches = search_model_memory(words)
    if not matches:
        return "No prior mistakes found."
    lines = []
    for m in matches[:20]:
        lines.append(
            f"- keyword={m['keyword']}; mistake={m['mistake']}; correction={m['human_correction']}"
        )
    return "\n".join(lines)


def get_relevant_rejections(text: str, max_chars_message: int = 280) -> str:
    """
    Retrieve human-rejected cases whose message or reason overlaps current text (keyword match).
    """
    words = _context_words(text)
    rows = search_rejected_trades(words)
    if not rows:
        return "No prior human rejections matched this message."
    lines = []
    for r in rows[:20]:
        msg = str(r["raw_message"] or "").replace("\n", " ").strip()
        if len(msg) > max_chars_message:
            msg = msg[: max_chars_message - 3] + "..."
        reason = str(r["rejection_reason"] or "").replace("\n", " ").strip()
        if not reason:
            reason = "(no reason given)"
        lines.append(f"- message_excerpt={msg!r}; human_rejected_because={reason!r}")
    return "\n".join(lines)


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default



def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _looks_trade_like(text: str) -> bool:
    """
    Fast heuristic to detect local trade-like messages even if LLM returns empty trades.
    """
    t = (text or "").lower()
    has_digits = bool(re.search(r"\d", t))
    has_bale = bool(re.search(r"\b\d+\s*b\b|\b\d+\s*bales?\b", t))
    has_cf = " cf " in f" {t} " or "cf " in t
    has_big_price = bool(re.search(r"\b\d{4,6}\b", t))
    has_cityish = any(k in t for k in ["multan", "khanewal", "bahawalpur", "haroonabad", "mahrab", "pur", "tounsa"])
    return has_digits and ((has_cf and has_big_price) or (has_bale and has_big_price) or (has_cityish and has_big_price))


def extract_trade(text: str, received_timestamp: Optional[str] = None) -> Dict:
    """
    Extract trade using Gemini + contextual memories and route by confidence.
    """
    raw_text = (text or "").strip()
    if not raw_text:
        return {"ok": False, "status": "skipped", "reason": "empty_text"}

    timestamp = received_timestamp or datetime.now().isoformat(sep=" ", timespec="seconds")
    preprocessed = preprocess_text(raw_text)
    relevant_memories = get_relevant_memories(preprocessed)
    relevant_rejections = get_relevant_rejections(preprocessed)

    system_prompt = (
        "You are a Pakistani commodities analyst extracting physical trades. "
        "Ignore international futures (ICE COTTON). "
        "A single message can contain multiple trades, extract ALL valid local physical trades. "
        "Calculate 'price_per_kg'. For cotton, if price > 5000, treat as per Maund and divide by 37.324 "
        "(because 1 maund = 37.324 kg). For non-cotton commodities, if price > 5000 treat per Maund and divide by 40. "
        f"PAST MISTAKES TO AVOID:\n{relevant_memories}\n\n"
        f"HUMAN-REJECTED CASES (similar messages were not valid trades; respect these reasons):\n{relevant_rejections}"
    )

    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "reasoning_step": types.Schema(type=types.Type.STRING),
            "trades": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "confidence_score": types.Schema(type=types.Type.INTEGER),
                        "city": types.Schema(type=types.Type.STRING),
                        "commodity": types.Schema(type=types.Type.STRING),
                        "quantity": types.Schema(type=types.Type.INTEGER),
                        "original_price": types.Schema(type=types.Type.NUMBER),
                        "price_per_kg": types.Schema(type=types.Type.NUMBER),
                    },
                    required=[
                        "confidence_score",
                        "city",
                        "commodity",
                        "quantity",
                        "original_price",
                        "price_per_kg",
                    ],
                ),
            ),
        },
        required=["reasoning_step", "trades"],
    )

    try:
        client = genai.Client()
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=preprocessed,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.1,
            ),
        )
        data = json.loads((response.text or "{}").strip() or "{}")
    except Exception as exc:
        insert_pending_trade(
            timestamp=timestamp,
            raw_message=raw_text,
            city="Unknown",
            commodity="Unknown",
            quantity=0,
            original_price=0.0,
            price_per_kg=0.0,
            confidence_score=0.0,
            ai_reasoning=f"Gemini error: {exc}",
        )
        return {"ok": False, "status": "pending", "reason": str(exc)}

    reasoning = str(data.get("reasoning_step", "")).strip()
    trades = data.get("trades") or []
    if not isinstance(trades, list):
        trades = []

    approved_count = 0
    pending_count = 0
    processed_trades = []

    for t in trades:
        confidence = max(0, min(100, _safe_int(t.get("confidence_score"), 0)))
        city = str(t.get("city", "Unknown") or "Unknown").strip()
        commodity = str(t.get("commodity", "Unknown") or "Unknown").strip()
        quantity = _safe_int(t.get("quantity"), 0)
        original_price = _safe_float(t.get("original_price"), 0.0)
        price_per_kg = _safe_float(t.get("price_per_kg"), 0.0)

        # Safety normalization if model omitted/failed numeric conversion.
        if price_per_kg <= 0 and original_price > 0:
            if original_price > 5000:
                if commodity.lower() == "cotton":
                    price_per_kg = original_price / COTTON_MAUND_KG
                else:
                    price_per_kg = original_price / 40.0
            else:
                price_per_kg = original_price

        payload = {
            "timestamp": timestamp,
            "city": city,
            "commodity": commodity,
            "quantity": quantity,
            "original_price": original_price,
            "price_per_kg": price_per_kg,
            "confidence_score": confidence,
            "ai_reasoning": reasoning,
            "raw_message": raw_text,
        }
        processed_trades.append(payload)

        # HITL-first mode: always route to pending queue for human validation/teaching.
        insert_pending_trade(
            timestamp=timestamp,
            raw_message=raw_text,
            city=city,
            commodity=commodity,
            quantity=quantity,
            original_price=original_price,
            price_per_kg=price_per_kg,
            confidence_score=float(confidence),
            ai_reasoning=reasoning,
        )
        pending_count += 1

    if approved_count == 0 and pending_count == 0:
        # Do NOT insert ai_empty_extraction into pending - user doesn't want those in the queue.
        return {"ok": True, "status": "skipped", "approved_count": 0, "pending_count": 0, "trades": []}
    status = "pending"
    return {
        "ok": True,
        "status": status,
        "approved_count": approved_count,
        "pending_count": pending_count,
        "trades": processed_trades,
    }
