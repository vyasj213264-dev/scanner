"""
Watchlist service — CRUD operations against the SQLite watchlists tables.
"""
import os
import sqlite3
from typing import List, Optional

DB_PATH = os.environ.get("DB_PATH", "scanner.db")


# ---------------------------------------------------------------------------
# Watchlist CRUD
# ---------------------------------------------------------------------------

def get_watchlists(user_id: int) -> List[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, created_at FROM watchlists WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def create_watchlist(user_id: int, name: str) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "INSERT INTO watchlists (user_id, name) VALUES (?, ?)", (user_id, name)
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, created_at FROM watchlists WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)


def delete_watchlist(watchlist_id: int, user_id: int) -> bool:
    """Delete only if owned by user_id."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM watchlists WHERE id = ? AND user_id = ?", (watchlist_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0


def rename_watchlist(watchlist_id: int, user_id: int, new_name: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "UPDATE watchlists SET name = ? WHERE id = ? AND user_id = ?",
            (new_name, watchlist_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Watchlist Stock CRUD
# ---------------------------------------------------------------------------

def get_watchlist_stocks(watchlist_id: int, user_id: int) -> Optional[List[dict]]:
    """Returns tickers with live screen_data. Returns None if watchlist not owned."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        # Verify ownership
        wl = conn.execute(
            "SELECT id FROM watchlists WHERE id = ? AND user_id = ?", (watchlist_id, user_id)
        ).fetchone()
        if wl is None:
            return None

        # Join with screen_data for live metrics
        rows = conn.execute(
            """
            SELECT s.*
            FROM watchlist_stocks ws
            LEFT JOIN screen_data s ON s.Ticker = ws.ticker
            WHERE ws.watchlist_id = ?
            ORDER BY ws.added_at DESC
            """,
            (watchlist_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_stock_to_watchlist(watchlist_id: int, user_id: int, ticker: str) -> bool:
    """Add ticker to watchlist. Returns False if not owner or ticker already in list."""
    ticker = ticker.upper().strip()
    with sqlite3.connect(DB_PATH) as conn:
        # Verify ownership
        wl = conn.execute(
            "SELECT id FROM watchlists WHERE id = ? AND user_id = ?", (watchlist_id, user_id)
        ).fetchone()
        if wl is None:
            return False
        try:
            conn.execute(
                "INSERT INTO watchlist_stocks (watchlist_id, ticker) VALUES (?, ?)",
                (watchlist_id, ticker),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Already exists


def remove_stock_from_watchlist(watchlist_id: int, user_id: int, ticker: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        wl = conn.execute(
            "SELECT id FROM watchlists WHERE id = ? AND user_id = ?", (watchlist_id, user_id)
        ).fetchone()
        if wl is None:
            return False
        cur = conn.execute(
            "DELETE FROM watchlist_stocks WHERE watchlist_id = ? AND ticker = ?",
            (watchlist_id, ticker.upper()),
        )
        conn.commit()
        return cur.rowcount > 0


def ticker_in_watchlists(user_id: int, ticker: str) -> List[int]:
    """Return list of watchlist IDs that contain this ticker for the user."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT ws.watchlist_id FROM watchlist_stocks ws
            INNER JOIN watchlists w ON w.id = ws.watchlist_id
            WHERE w.user_id = ? AND ws.ticker = ?
            """,
            (user_id, ticker.upper()),
        ).fetchall()
        return [r[0] for r in rows]
