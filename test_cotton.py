import os
import json
import re
import csv
from datetime import datetime
from pathlib import Path
from google import genai
from google.genai import types
from dotenv import load_dotenv
from agri_dashboard.whatsapp_parser import parse_whatsapp_export

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(REPO_ROOT, "agri_dashboard", ".env"))
OUTPUT_DIR = Path(REPO_ROOT) / "agri_dashboard" / "outputs"
MAX_MESSAGES = 3

client = genai.Client()


def extract_cotton_data(text_chunk, received_timestamp: str):
    system_instruction = f"""
    You are an intelligent agricultural commodities analyst in Pakistan.
    Your goal is to extract local physical cotton trades from unstructured broker messages.
    The messages will be messy, containing mixed Urdu/English, international futures (like ICE COTTON), and random noise.

    INSTRUCTIONS:
    1. Read the text and ignore international/futures markets. Find the local physical trades.
    2. Identify the City, the Commodity/Brand, the Quantity, and the Price.
    3. Apply common sense to the price: If the price is a large number (e.g., > 5000), it is likely per Maund.
       For cotton, use this exact conversion: 1 Maund = 37.324 kg.
       You MUST calculate per-kg price as: original_price / 37.324
    4. For each extracted trade, find a relevant trade datetime from the message text (e.g., 'Thu-21-Aug-2025 07:55 PM').
    5. If you cannot find a reliable trade datetime in the text, use this fallback timestamp exactly: {received_timestamp}
    6. First, write down your reasoning in the 'reasoning_step' field. Then, output the extracted trades.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=text_chunk,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.1,  # Slight flexibility for reading messy text
                response_schema=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "reasoning_step": types.Schema(
                            type=types.Type.STRING,
                            description="Explain your thought process. What local trades do you see? What is the math for the per-kg price?",
                        ),
                        "trades": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(
                                type=types.Type.OBJECT,
                                properties={
                                    "city": types.Schema(type=types.Type.STRING),
                                    "commodity": types.Schema(type=types.Type.STRING),
                                    "quantity_bales": types.Schema(type=types.Type.INTEGER),
                                    "original_price": types.Schema(type=types.Type.NUMBER),
                                    "price_per_kg": types.Schema(type=types.Type.NUMBER),
                                    "confidence": types.Schema(
                                        type=types.Type.NUMBER,
                                        description="Confidence score from 0 to 1 for this extracted trade.",
                                    ),
                                    "trade_timestamp": types.Schema(
                                        type=types.Type.STRING,
                                        description="Trade date/time. Prefer date/time found in message text; otherwise fallback timestamp.",
                                    ),
                                    "timestamp_source": types.Schema(
                                        type=types.Type.STRING,
                                        description="Use 'from_message' if inferred from text, else 'fallback_received'.",
                                    ),
                                },
                            ),
                        ),
                    },
                ),
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return None


def write_outputs(rows):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUTPUT_DIR / f"test_cotton_{stamp}.json"
    csv_path = OUTPUT_DIR / f"test_cotton_{stamp}.csv"

    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(rows, jf, ensure_ascii=False, indent=2)

    fieldnames = [
        "message_index",
        "message",
        "received_timestamp",
        "trade_timestamp",
        "final_timestamp",
        "timestamp_source",
        "reasoning_step",
        "city",
        "commodity",
        "quantity_bales",
        "original_price",
        "price_per_kg",
        "confidence",
        "status",
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as cf:
        writer = csv.DictWriter(
            cf,
            fieldnames=fieldnames,
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        for row in rows:
            cleaned = {}
            for k in fieldnames:
                v = row.get(k, "")
                if isinstance(v, str):
                    # Keep message readable in Excel by flattening line breaks.
                    v = re.sub(r"\s*\r?\n\s*", " | ", v).strip()
                cleaned[k] = v
            writer.writerow(cleaned)

    return json_path, csv_path


def _select_cotton_messages(content: str, max_messages: int = MAX_MESSAGES):
    parsed = parse_whatsapp_export(content, group_name="Business Club Commodities")
    cotton_keywords = ("cotton", "kapas", "phutti", "cf", "کپاس")

    candidates = []
    for msg in parsed:
        text = (msg.get("message") or "").strip()
        low = text.lower()
        if not text:
            continue
        if not any(k in low for k in cotton_keywords):
            continue
        if not any(ch.isdigit() for ch in text):
            continue
        candidates.append(msg)

    # Fallback: if too few cotton-tagged messages, use any numeric messages.
    if len(candidates) < max_messages:
        for msg in parsed:
            text = (msg.get("message") or "").strip()
            if text and any(ch.isdigit() for ch in text) and msg not in candidates:
                candidates.append(msg)
            if len(candidates) >= max_messages:
                break

    return candidates[:max_messages]


def main():
    repo_root = REPO_ROOT
    file_path = os.path.join(repo_root, "WhatsApp Chat with Business Club Commodities.txt")

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()

        messages = _select_cotton_messages(content, max_messages=MAX_MESSAGES)
        print(f"Selected {len(messages)} candidate messages.")
        output_rows = []

        for i, msg_obj in enumerate(messages, 1):
            msg = (msg_obj.get("message") or "").strip()
            msg_ts = msg_obj.get("timestamp")
            received_timestamp = (
                msg_ts.isoformat(sep=" ", timespec="seconds")
                if isinstance(msg_ts, datetime)
                else datetime.now().isoformat(sep=" ", timespec="seconds")
            )

            if any(char.isdigit() for char in msg):
                result = extract_cotton_data(msg, received_timestamp)
                if result:
                    print(f"--- Message {i} ---")
                    print(f"AI Thinking: {result.get('reasoning_step')}")
                    print(f"Extracted Trades: {json.dumps(result.get('trades'), indent=2)}\n")
                    trades = result.get("trades") or []
                    if trades:
                        for t in trades:
                            output_rows.append(
                                {
                                    "message_index": i,
                                    "message": msg,
                                    "received_timestamp": received_timestamp,
                                    "trade_timestamp": t.get("trade_timestamp", ""),
                                    "final_timestamp": t.get("trade_timestamp", "") or received_timestamp,
                                    "timestamp_source": t.get("timestamp_source", "") or ("from_message" if t.get("trade_timestamp") else "fallback_received"),
                                    "reasoning_step": result.get("reasoning_step", ""),
                                    "city": t.get("city", ""),
                                    "commodity": t.get("commodity", ""),
                                    "quantity_bales": t.get("quantity_bales", ""),
                                    "original_price": t.get("original_price", ""),
                                    "price_per_kg": t.get("price_per_kg", ""),
                                    "confidence": t.get("confidence", ""),
                                    "status": "accepted",
                                }
                            )
                    else:
                        output_rows.append(
                            {
                                "message_index": i,
                                "message": msg,
                                "received_timestamp": received_timestamp,
                                "trade_timestamp": "",
                                "final_timestamp": received_timestamp,
                                "timestamp_source": "fallback_received",
                                "reasoning_step": result.get("reasoning_step", ""),
                                "city": "",
                                "commodity": "",
                                "quantity_bales": "",
                                "original_price": "",
                                "price_per_kg": "",
                                "confidence": "",
                                "status": "rejected",
                            }
                        )
                else:
                    print(f"--- Message {i}: No trades found ---\n")
                    output_rows.append(
                        {
                            "message_index": i,
                            "message": msg,
                            "received_timestamp": received_timestamp,
                            "trade_timestamp": "",
                            "final_timestamp": received_timestamp,
                            "timestamp_source": "fallback_received",
                            "reasoning_step": "",
                            "city": "",
                            "commodity": "",
                            "quantity_bales": "",
                            "original_price": "",
                            "price_per_kg": "",
                            "confidence": "",
                            "status": "error",
                        }
                    )

        json_path, csv_path = write_outputs(output_rows)
        print(f"Saved JSON output: {json_path}")
        print(f"Saved CSV output:  {csv_path}")

    except FileNotFoundError:
        print(f"File not found: {file_path}")


if __name__ == "__main__":
    main()
