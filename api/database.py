"""
SQLite database connection and query utilities.
"""
import sqlite3
from contextlib import contextmanager
from typing import Any, List, Optional, Tuple

from api.config import DB_PATH


@contextmanager
def get_db():
    """Context manager that yields a database connection and auto-closes."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(sql: str, params: Tuple = ()) -> List[dict]:
    """Execute a SELECT query and return all rows as a list of dicts."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def fetch_one(sql: str, params: Tuple = ()) -> Optional[dict]:
    """Execute a SELECT query and return a single row as a dict."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None


def get_last_updated() -> Optional[str]:
    """Returns the most recent data date from the screen_data table."""
    result = fetch_one("SELECT MAX(Date) as last_date FROM screen_data")
    return result.get("last_date") if result else None


def get_universe_count_in_db() -> int:
    """Returns the total number of tickers in the database."""
    result = fetch_one("SELECT COUNT(*) as cnt FROM screen_data")
    return result.get("cnt", 0) if result else 0
