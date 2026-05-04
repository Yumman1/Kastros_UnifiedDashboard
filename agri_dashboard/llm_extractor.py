"""
LLM-based extraction of commodity market data from unstructured WhatsApp text.
Uses Google Gemini (free API) to parse messages and produce data for the Live Rates table.
Legacy module: prefer using extractor.py directly.
"""

from extractor import process_message_to_db_format


def extract_market_data_from_text(text: str):
    """
    Extract commodity, price, city from text using Gemini.
    Returns list of dicts: [{"commodity": "...", "price": 8500.0, "city": "Karachi"}, ...]
    """
    return process_message_to_db_format(text)
