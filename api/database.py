"""
SQLite database connection and query utilities.
"""
import sqlite3
from contextlib import contextmanager
from typing import Any, List, Optional, Tuple

from api.config import DB_PATH, DATABASE_URL

@contextmanager
def get_db():
    """Context manager that yields a database connection and auto-closes."""
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        import psycopg2
        import psycopg2.extras
        # Handle 'postgres://' vs 'postgresql://' safely
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1) if DATABASE_URL.startswith("postgres://") else DATABASE_URL
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.DictCursor)
        try:
            yield conn
        finally:
            conn.close()
    else:
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
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            sql = sql.replace('?', '%s')
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def fetch_one(sql: str, params: Tuple = ()) -> Optional[dict]:
    """Execute a SELECT query and return a single row as a dict."""
    with get_db() as conn:
        cursor = conn.cursor()
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            sql = sql.replace('?', '%s')
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None


def get_last_updated() -> Optional[str]:
    """Returns the most recent data date from the screen_data table."""
    try:
        result = fetch_one("SELECT MAX(Date) as last_date FROM screen_data")
        return result.get("last_date") if result else None
    except Exception:
        return None  # Handle empty fresh database


def get_universe_count_in_db() -> int:
    """Returns the total number of tickers in the database."""
    try:
        result = fetch_one("SELECT COUNT(*) as cnt FROM screen_data")
        return result.get("cnt", 0) if result else 0
    except Exception:
        return 0
