"""
Watchlist service — CRUD operations against the SQLite watchlists tables.
"""
import os
from typing import List, Optional

from api.database import get_db, get_user_db, fetch_all, fetch_one


# ---------------------------------------------------------------------------
# Watchlist CRUD
# ---------------------------------------------------------------------------

def get_watchlists(user_id: int) -> List[dict]:
    return fetch_all(
        "SELECT id, name, created_at FROM watchlists WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )


def create_watchlist(user_id: int, name: str) -> dict:
    with get_user_db() as conn:
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
    """Delete only if owned by user_id. Removes child stocks first (FK constraint)."""
    with get_user_db() as conn:
        cursor = conn.cursor()
        from api.config import DATABASE_URL
        is_pg = DATABASE_URL and DATABASE_URL.startswith("postgres")

        # Verify ownership first
        check_sql = "SELECT id FROM watchlists WHERE id = ? AND user_id = ?"
        if is_pg: check_sql = check_sql.replace('?', '%s')
        cursor.execute(check_sql, (watchlist_id, user_id))
        if cursor.fetchone() is None:
            return False

        # Delete child rows first (watchlist_stocks has FK → watchlists)
        child_sql = "DELETE FROM watchlist_stocks WHERE watchlist_id = ?"
        if is_pg: child_sql = child_sql.replace('?', '%s')
        cursor.execute(child_sql, (watchlist_id,))

        # Now delete the watchlist itself
        parent_sql = "DELETE FROM watchlists WHERE id = ? AND user_id = ?"
        if is_pg: parent_sql = parent_sql.replace('?', '%s')
        cursor.execute(parent_sql, (watchlist_id, user_id))
        conn.commit()
        return cursor.rowcount > 0


def rename_watchlist(watchlist_id: int, user_id: int, new_name: str) -> bool:
    with get_user_db() as conn:
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

def get_watchlist_stocks(
    watchlist_id: int,
    user_id: int,
    min_market_cap: Optional[float] = None,
    min_adr: Optional[float] = None,
    max_adr: Optional[float] = None,
    min_price: Optional[float] = None,
    include_sectors: Optional[List[str]] = None,
    exclude_sectors: Optional[List[str]] = None,
    include_industries: Optional[List[str]] = None,
    exclude_industries: Optional[List[str]] = None,
) -> Optional[List[dict]]:
    """Returns tickers with live screen_data. Returns None if watchlist not owned."""
    # Verify ownership
    wl = fetch_one(
        "SELECT id FROM watchlists WHERE id = ? AND user_id = ?", 
        (watchlist_id, user_id)
    )
    if wl is None:
        return None

    extra_where = ""
    params = [watchlist_id]

    if min_market_cap is not None:
        extra_where += " AND s.Market_Cap >= ?"
        params.append(min_market_cap)
    if min_adr is not None:
        extra_where += " AND s.ADR_20 >= ?"
        params.append(min_adr)
    if max_adr is not None:
        extra_where += " AND s.ADR_20 <= ?"
        params.append(max_adr)
    if min_price is not None:
        extra_where += " AND s.Close >= ?"
        params.append(min_price)

    if include_sectors:
        placeholders = ', '.join(['?' for _ in include_sectors])
        extra_where += f" AND s.Sector IN ({placeholders})"
        params.extend(include_sectors)
    if exclude_sectors:
        placeholders = ', '.join(['?' for _ in exclude_sectors])
        extra_where += f" AND s.Sector NOT IN ({placeholders})"
        params.extend(exclude_sectors)
    if include_industries:
        placeholders = ', '.join(['?' for _ in include_industries])
        extra_where += f" AND s.Industry IN ({placeholders})"
        params.extend(include_industries)
    if exclude_industries:
        placeholders = ', '.join(['?' for _ in exclude_industries])
        extra_where += f" AND s.Industry NOT IN ({placeholders})"
        params.extend(exclude_industries)

    # Join with screen_data for live metrics using fetch_all so it hits the live database
    latest_date_query = "(SELECT MAX(Date) FROM industry_ranks)"
    sql = f"""
        SELECT ws.ticker AS "Ticker", s.*,
        sr.Rank_1D AS Sector_Rank_1D, sr.Rank_1W AS Sector_Rank_1W,
        sr.Rank_1M AS Sector_Rank_1M, sr.Rank_3M AS Sector_Rank_3M, sr.Rank_6M AS Sector_Rank_6M,
        ir.Rank_1D AS Industry_Rank_1D, ir.Rank_1W AS Industry_Rank_1W,
        ir.Rank_1M AS Industry_Rank_1M, ir.Rank_3M AS Industry_Rank_3M, ir.Rank_6M AS Industry_Rank_6M
        FROM watchlist_stocks ws
        LEFT JOIN screen_data s ON s.Ticker = ws.ticker
        LEFT JOIN industry_ranks sr ON s.Sector = sr.Name AND sr.Category = 'Sector' AND sr.Date = {latest_date_query}
        LEFT JOIN industry_ranks ir ON s.Industry = ir.Name AND ir.Category = 'Industry' AND ir.Date = {latest_date_query}
        WHERE ws.watchlist_id = ?{extra_where}
        ORDER BY ws.added_at DESC
    """
    return fetch_all(sql, tuple(params))


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
        
    with get_user_db() as conn:
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
        
    with get_user_db() as conn:
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
