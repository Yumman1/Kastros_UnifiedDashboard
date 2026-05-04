"""
Debug log for extraction: raw message, Gemini output, source.
Stored in SQLite for persistence across restarts.
"""

import json
import os
from datetime import datetime

_agri_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_agri_dir, "market_data.db")
DEBUG_TABLE = "extraction_debug_log"
MAX_ENTRIES = 200


def _get_conn():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_debug_table():
    conn = _get_conn()
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {DEBUG_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            raw_message TEXT NOT NULL,
            gemini_output TEXT,
            gemini_error TEXT,
            records_extracted INTEGER DEFAULT 0,
            records_json TEXT
        )
    """)
    conn.commit()
    conn.close()


def append_log(
    raw_message: str,
    source: str,
    gemini_output: str = None,
    gemini_error: str = None,
    records_extracted: int = 0,
    records_json: str = None,
):
    init_debug_table()
    conn = _get_conn()
    conn.execute(
        f"""
        INSERT INTO {DEBUG_TABLE}
        (created_at, source, raw_message, gemini_output, gemini_error, records_extracted, records_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(),
            source or "Unknown",
            raw_message[:2000] if raw_message else "",
            gemini_output[:2000] if gemini_output else None,
            gemini_error[:1000] if gemini_error else None,
            records_extracted,
            records_json[:2000] if records_json else None,
        ),
    )
    conn.commit()
    # Prune old entries
    cursor = conn.execute(
        f"SELECT id FROM {DEBUG_TABLE} ORDER BY id DESC LIMIT 1 OFFSET ?",
        (MAX_ENTRIES,),
    )
    row = cursor.fetchone()
    if row:
        conn.execute(f"DELETE FROM {DEBUG_TABLE} WHERE id <= ?", (row["id"],))
        conn.commit()
    conn.close()


def get_recent_logs(limit: int = 50):
    init_debug_table()
    conn = _get_conn()
    rows = conn.execute(
        f"""
        SELECT created_at, source, raw_message, gemini_output, gemini_error,
               records_extracted, records_json
        FROM {DEBUG_TABLE}
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
