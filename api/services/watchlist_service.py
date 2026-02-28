"""
Watchlist service — CRUD operations against the SQLite watchlists tables.
"""
import os
from typing import List, Optional

from api.database import get_db, fetch_all, fetch_one


# ---------------------------------------------------------------------------
# Watchlist CRUD
# ---------------------------------------------------------------------------

def get_watchlists(user_id: int) -> List[dict]:
    return fetch_all(
        "SELECT id, name, created_at FROM watchlists WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )


def create_watchlist(user_id: int, name: str) -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        # Handle SQLite vs Postgres ? parameter substitution
        from api.config import DATABASE_URL
        sql = "INSERT INTO watchlists (user_id, name) VALUES (?, ?) RETURNING id, name, created_at"
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            sql = sql.replace('?', '%s')
        
        cursor.execute(sql, (user_id, name))
        row = cursor.fetchone()
        conn.commit()
        
        if row is None:
            # Fallback for old SQLite versions lacking RETURNING
            last_id = cursor.lastrowid
            sql_fetch = "SELECT id, name, created_at FROM watchlists WHERE id = ?"
            if DATABASE_URL and DATABASE_URL.startswith("postgres"):
                sql_fetch = sql_fetch.replace('?', '%s')
            cursor.execute(sql_fetch, (last_id,))
            row = cursor.fetchone()
            
        return dict(row)


def delete_watchlist(watchlist_id: int, user_id: int) -> bool:
    """Delete only if owned by user_id."""
    with get_db() as conn:
        cursor = conn.cursor()
        sql = "DELETE FROM watchlists WHERE id = ? AND user_id = ?"
        from api.config import DATABASE_URL
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            sql = sql.replace('?', '%s')
        cursor.execute(sql, (watchlist_id, user_id))
        conn.commit()
        return cursor.rowcount > 0


def rename_watchlist(watchlist_id: int, user_id: int, new_name: str) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        sql = "UPDATE watchlists SET name = ? WHERE id = ? AND user_id = ?"
        from api.config import DATABASE_URL
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            sql = sql.replace('?', '%s')
        cursor.execute(sql, (new_name, watchlist_id, user_id))
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Watchlist Stock CRUD
# ---------------------------------------------------------------------------

def get_watchlist_stocks(watchlist_id: int, user_id: int) -> Optional[List[dict]]:
    """Returns tickers with live screen_data. Returns None if watchlist not owned."""
    # Verify ownership
    wl = fetch_one(
        "SELECT id FROM watchlists WHERE id = ? AND user_id = ?", 
        (watchlist_id, user_id)
    )
    if wl is None:
        return None

    # Join with screen_data for live metrics using fetch_all so it hits the live database
    return fetch_all(
        """
        SELECT ws.ticker AS "Ticker", s.*
        FROM watchlist_stocks ws
        LEFT JOIN screen_data s ON s.Ticker = ws.ticker
        WHERE ws.watchlist_id = ?
        ORDER BY ws.added_at DESC
        """,
        (watchlist_id,)
    )


def add_stock_to_watchlist(watchlist_id: int, user_id: int, ticker: str) -> bool:
    """Add ticker to watchlist. Returns False if not owner or ticker already in list."""
    ticker = ticker.upper().strip()
    
    # Verify ownership
    wl = fetch_one(
        "SELECT id FROM watchlists WHERE id = ? AND user_id = ?", 
        (watchlist_id, user_id)
    )
    if wl is None:
        return False
        
    with get_db() as conn:
        cursor = conn.cursor()
        sql = "INSERT INTO watchlist_stocks (watchlist_id, ticker) VALUES (?, ?)"
        from api.config import DATABASE_URL
        # Postgres ON CONFLICT DO NOTHING vs SQLite INSERT OR IGNORE
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            sql = "INSERT INTO watchlist_stocks (watchlist_id, ticker) VALUES (%s, %s) ON CONFLICT DO NOTHING"
        else:
            sql = "INSERT OR IGNORE INTO watchlist_stocks (watchlist_id, ticker) VALUES (?, ?)"
            
        cursor.execute(sql, (watchlist_id, ticker))
        conn.commit()
        # rowcount represents inserted rows. If 0, it means conflict/ignored
        return cursor.rowcount > 0


def remove_stock_from_watchlist(watchlist_id: int, user_id: int, ticker: str) -> bool:
    wl = fetch_one(
        "SELECT id FROM watchlists WHERE id = ? AND user_id = ?", 
        (watchlist_id, user_id)
    )
    if wl is None:
        return False
        
    with get_db() as conn:
        cursor = conn.cursor()
        sql = "DELETE FROM watchlist_stocks WHERE watchlist_id = ? AND ticker = ?"
        from api.config import DATABASE_URL
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            sql = sql.replace('?', '%s')
            
        cursor.execute(sql, (watchlist_id, ticker.upper()))
        conn.commit()
        return cursor.rowcount > 0


def ticker_in_watchlists(user_id: int, ticker: str) -> List[int]:
    """Return list of watchlist IDs that contain this ticker for the user."""
    rows = fetch_all(
        """
        SELECT ws.watchlist_id 
        FROM watchlist_stocks ws
        INNER JOIN watchlists w ON w.id = ws.watchlist_id
        WHERE w.user_id = ? AND ws.ticker = ?
        """,
        (user_id, ticker.upper())
    )
    return [r['watchlist_id'] for r in rows]
