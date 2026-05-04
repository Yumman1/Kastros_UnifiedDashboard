"""
SQLite database layer for HITL + contextual memory workflow.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Iterable, List, Optional


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "market_data.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS market_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                city TEXT,
                commodity TEXT,
                quantity INTEGER,
                original_price REAL,
                price_per_kg REAL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                raw_message TEXT NOT NULL,
                city TEXT,
                commodity TEXT,
                quantity INTEGER,
                original_price REAL,
                price_per_kg REAL,
                confidence_score REAL,
                ai_reasoning TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS model_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                mistake TEXT NOT NULL,
                human_correction TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS master_dictionary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slang_word TEXT NOT NULL,
                standard_word TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS rejected_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_message TEXT NOT NULL,
                rejection_reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def insert_market_trade(
    timestamp: str,
    city: str,
    commodity: str,
    quantity: Optional[int],
    original_price: Optional[float],
    price_per_kg: Optional[float],
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO market_trades (timestamp, city, commodity, quantity, original_price, price_per_kg)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (timestamp, city, commodity, quantity, original_price, price_per_kg),
        )
        return int(cur.lastrowid)


def fetch_market_trades(limit: Optional[int] = None) -> List[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.cursor()
        if limit is None:
            cur.execute("SELECT * FROM market_trades ORDER BY timestamp DESC, id DESC")
        else:
            cur.execute("SELECT * FROM market_trades ORDER BY timestamp DESC, id DESC LIMIT ?", (int(limit),))
        return cur.fetchall()


def delete_market_trades(trade_ids: Iterable[int]) -> int:
    """Delete many rows in one transaction; returns number of rows deleted."""
    ids = list({int(i) for i in trade_ids})
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM market_trades WHERE id IN ({placeholders})", ids)
        conn.commit()
        return int(cur.rowcount or 0)


def insert_pending_trade(
    timestamp: str,
    raw_message: str,
    city: str,
    commodity: str,
    quantity: Optional[int],
    original_price: Optional[float],
    price_per_kg: Optional[float],
    confidence_score: float,
    ai_reasoning: str,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pending_trades
            (timestamp, raw_message, city, commodity, quantity, original_price, price_per_kg, confidence_score, ai_reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                raw_message,
                city,
                commodity,
                quantity,
                original_price,
                price_per_kg,
                confidence_score,
                ai_reasoning,
            ),
        )
        return int(cur.lastrowid)


def fetch_pending_trades(limit: Optional[int] = None) -> List[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.cursor()
        # Exclude ai_empty_extraction - those should not appear in the validation queue
        base = "SELECT * FROM pending_trades WHERE (ai_reasoning IS NULL OR ai_reasoning NOT LIKE ?)"
        params: tuple = ("%ai_empty_extraction%",)
        if limit is not None:
            base += " ORDER BY id DESC LIMIT ?"
            params = params + (int(limit),)
        else:
            base += " ORDER BY id DESC"
        cur.execute(base, params)
        return cur.fetchall()


def delete_pending_trade(trade_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM pending_trades WHERE id = ?", (int(trade_id),))


def approve_all_pending() -> int:
    """Approve every row returned by fetch_pending_trades (same filter as the queue)."""
    rows = list(fetch_pending_trades())
    if not rows:
        return 0
    with get_connection() as conn:
        cur = conn.cursor()
        for row in rows:
            cur.execute(
                """
                INSERT INTO market_trades (timestamp, city, commodity, quantity, original_price, price_per_kg)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["timestamp"],
                    str(row["city"] or ""),
                    str(row["commodity"] or ""),
                    int(row["quantity"] or 0),
                    float(row["original_price"] or 0),
                    float(row["price_per_kg"] or 0),
                ),
            )
            cur.execute("DELETE FROM pending_trades WHERE id = ?", (int(row["id"]),))
        conn.commit()
    return len(rows)


def reject_all_pending(rejection_reason: str = "") -> int:
    """Reject every row in the queue; optional shared reason stored on each rejected row."""
    rows = list(fetch_pending_trades())
    if not rows:
        return 0
    reason = rejection_reason.strip()
    created = datetime.now().isoformat(sep=" ", timespec="seconds")
    with get_connection() as conn:
        cur = conn.cursor()
        for row in rows:
            cur.execute(
                """
                INSERT INTO rejected_trades (raw_message, rejection_reason, created_at)
                VALUES (?, ?, ?)
                """,
                (str(row["raw_message"] or "").strip(), reason, created),
            )
            cur.execute("DELETE FROM pending_trades WHERE id = ?", (int(row["id"]),))
        conn.commit()
    return len(rows)


def insert_rejected_trade(raw_message: str, rejection_reason: str) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO rejected_trades (raw_message, rejection_reason, created_at)
            VALUES (?, ?, ?)
            """,
            (raw_message.strip(), rejection_reason.strip(), datetime.now().isoformat(sep=" ", timespec="seconds")),
        )
        return int(cur.lastrowid)


def search_rejected_trades(words: Iterable[str]) -> List[sqlite3.Row]:
    """Rows where any keyword appears in stored message or rejection reason (for RAG context)."""
    words = [w.strip().lower() for w in words if w and w.strip()]
    if not words:
        return []
    hay = "LOWER(COALESCE(raw_message,'') || ' ' || COALESCE(rejection_reason,''))"
    query = " OR ".join([f"{hay} LIKE ?"] * len(words))
    params = tuple(f"%{w}%" for w in words)
    with get_connection() as conn:
        return conn.execute(
            f"SELECT * FROM rejected_trades WHERE {query} ORDER BY id DESC LIMIT 25",
            params,
        ).fetchall()


def insert_model_memory(keyword: str, mistake: str, human_correction: str) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO model_memory (keyword, mistake, human_correction)
            VALUES (?, ?, ?)
            """,
            (keyword.strip(), mistake.strip(), human_correction.strip()),
        )
        return int(cur.lastrowid)


def fetch_model_memory() -> List[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM model_memory ORDER BY id DESC").fetchall()


def search_model_memory(words: Iterable[str]) -> List[sqlite3.Row]:
    words = [w.strip().lower() for w in words if w and w.strip()]
    if not words:
        return []
    query = " OR ".join(["LOWER(keyword) LIKE ?"] * len(words))
    params = tuple(f"%{w}%" for w in words)
    with get_connection() as conn:
        return conn.execute(
            f"SELECT * FROM model_memory WHERE {query} ORDER BY id DESC",
            params,
        ).fetchall()


def insert_master_dictionary(slang_word: str, standard_word: str) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO master_dictionary (slang_word, standard_word)
            VALUES (?, ?)
            """,
            (slang_word.strip(), standard_word.strip()),
        )
        return int(cur.lastrowid)


def fetch_master_dictionary() -> List[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM master_dictionary ORDER BY id DESC").fetchall()


def delete_master_dictionary(item_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM master_dictionary WHERE id = ?", (int(item_id),))
