"""
SQLite database layer for HITL + contextual memory workflow.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Union


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _default_db_path() -> str:
    # Vercel serverless: project dir is read-only; only /tmp is writable.
    if os.getenv("VERCEL") or os.getenv("DATABASE_USE_TMP", "").lower() in ("1", "true", "yes"):
        return os.path.join("/tmp", "market_data.db")
    return os.path.join(BASE_DIR, "market_data.db")


DB_PATH = os.environ.get("DATABASE_PATH") or _default_db_path()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS market_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                commodity TEXT NOT NULL,
                source TEXT,
                price REAL NOT NULL,
                city TEXT,
                sentiment_score REAL DEFAULT 0,
                raw_message TEXT
            )
            """
        )


def _timestamp_to_iso(ts: Union[datetime, str, None]) -> str:
    if ts is None:
        return datetime.now().isoformat(sep=" ", timespec="seconds")
    if isinstance(ts, datetime):
        return ts.isoformat(sep=" ", timespec="seconds")
    return str(ts)


def insert_market_data(
    timestamp: Union[datetime, str, None],
    commodity: str,
    source: str,
    price: float,
    city: str,
    sentiment_score: float = 0.0,
    raw_message: Optional[str] = None,
) -> int:
    """Insert a row into market_data (API + WhatsApp ingest)."""
    ts_str = _timestamp_to_iso(timestamp)
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO market_data (timestamp, commodity, source, price, city, sentiment_score, raw_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts_str,
                str(commodity or ""),
                str(source or ""),
                float(price),
                str(city or ""),
                float(sentiment_score or 0),
                raw_message if raw_message is not None else "",
            ),
        )
        return int(cur.lastrowid)


def get_recent_prices(days: int = 30) -> List[tuple]:
    cutoff = datetime.now() - timedelta(days=int(days))
    cutoff_s = cutoff.isoformat(sep=" ", timespec="seconds")
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, commodity, source, price, city, sentiment_score, raw_message
            FROM market_data
            WHERE datetime(timestamp) >= datetime(?)
            ORDER BY datetime(timestamp) DESC
            """,
            (cutoff_s,),
        ).fetchall()
    out: List[tuple] = []
    for row in rows:
        ts_raw = row["timestamp"]
        try:
            ts_dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except ValueError:
            ts_dt = ts_raw
        out.append(
            (
                ts_dt,
                row["commodity"],
                row["source"],
                row["price"],
                row["city"],
                row["sentiment_score"],
                row["raw_message"],
            )
        )
    return out


def get_todays_prices() -> List[tuple]:
    today = datetime.now().date().isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, commodity, source, price, city, sentiment_score, raw_message
            FROM market_data
            WHERE date(timestamp) = date(?)
            ORDER BY datetime(timestamp) DESC
            """,
            (today,),
        ).fetchall()
    out: List[tuple] = []
    for row in rows:
        ts_raw = row["timestamp"]
        try:
            ts_dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except ValueError:
            ts_dt = ts_raw
        out.append(
            (
                ts_dt,
                row["commodity"],
                row["source"],
                row["price"],
                row["city"],
                row["sentiment_score"],
                row["raw_message"],
            )
        )
    return out


def get_historic_data(
    commodity: Optional[str] = None,
    city: Optional[str] = None,
) -> List[tuple]:
    q = "SELECT timestamp, commodity, source, price, city, sentiment_score FROM market_data WHERE 1=1"
    params: List[str] = []
    if commodity:
        q += " AND commodity = ?"
        params.append(str(commodity))
    if city:
        q += " AND city = ?"
        params.append(str(city))
    q += " ORDER BY datetime(timestamp) ASC"
    with get_connection() as conn:
        rows = conn.execute(q, params).fetchall()
    out: List[tuple] = []
    for row in rows:
        ts_raw = row["timestamp"]
        try:
            ts_dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except ValueError:
            ts_dt = ts_raw
        out.append(
            (
                ts_dt,
                row["commodity"],
                row["source"],
                row["price"],
                row["city"],
                row["sentiment_score"],
            )
        )
    return out


def get_recent_entries_for_inspector(limit: int = 50) -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, timestamp, commodity, source, price, city, sentiment_score, raw_message
            FROM market_data
            ORDER BY datetime(timestamp) DESC, id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    entries: List[dict] = []
    for row in rows:
        ts_raw = row["timestamp"]
        try:
            ts_dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except ValueError:
            ts_dt = ts_raw
        entries.append(
            {
                "id": row["id"],
                "timestamp": ts_dt,
                "commodity": row["commodity"],
                "source": row["source"],
                "price": row["price"],
                "city": row["city"],
                "sentiment_score": row["sentiment_score"],
                "raw_message": row["raw_message"],
            }
        )
    return entries


def seed_data() -> None:
    """Sample rows for /seed and manual testing."""
    init_db()
    now = datetime.now()
    samples = [
        (now, "Cotton", "seed", 185.5, "Karachi", 0.1, "seed row"),
        (now, "Wheat", "seed", 92.0, "Lahore", 0.0, "seed row"),
    ]
    for ts, comm, src, price, cit, sent, raw in samples:
        insert_market_data(
            timestamp=ts,
            commodity=comm,
            source=src,
            price=price,
            city=cit,
            sentiment_score=sent,
            raw_message=raw,
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
