"""
SQLite database connection and query utilities.
"""
import sqlite3
from contextlib import contextmanager
from typing import Any, List, Optional, Tuple

from api.config import DB_PATH, USERS_DB_PATH, DATABASE_URL

@contextmanager
def get_db():
    """Context manager for scanner/screen_data database."""
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        import psycopg2
        import psycopg2.extras
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


@contextmanager
def get_user_db():
    """Context manager for user/watchlist database (separate from scanner.db)."""
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        import psycopg2
        import psycopg2.extras
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1) if DATABASE_URL.startswith("postgres://") else DATABASE_URL
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.DictCursor)
        try:
            yield conn
        finally:
            conn.close()
    else:
        # Use a SEPARATE SQLite file for user data so ingest.py never touches it
        conn = sqlite3.connect(USERS_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

COL_MAP = {
    'ticker': 'Ticker', 'date': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 
    'close': 'Close', 'volume': 'Volume',
    'sma_5': 'SMA_5', 'sma_9': 'SMA_9', 'sma_10': 'SMA_10', 'sma_20': 'SMA_20',
    'sma_21': 'SMA_21', 'sma_50': 'SMA_50', 'sma_100': 'SMA_100', 'sma_200': 'SMA_200',
    'rvol': 'RVOL', 'adr_20': 'ADR_20', 'pct_from_52w_high': 'Pct_From_52W_High',
    'in_stage_2': 'In_Stage_2', 'tight_setup': 'Tight_Setup', 
    'near_horizontal_resistance': 'Near_Horizontal_Resistance',
    'rs_raw': 'RS_Raw', 'inside_bar': 'Inside_Bar', 'golden_crossover': 'Golden_Crossover',
    'gap_up': 'Gap_Up', 'gap_down': 'Gap_Down', 'vcp_approximation': 'VCP_Approximation',
    'momentum_1d': 'Momentum_1D', 'momentum_1w': 'Momentum_1W', 'momentum_1m': 'Momentum_1M',
    'momentum_3m': 'Momentum_3M', 'momentum_6m': 'Momentum_6M', 'momentum_1y': 'Momentum_1Y',
    'rs_rating': 'RS_Rating', 'rs_rating_1m': 'RS_Rating_1M', 'rs_rating_3m': 'RS_Rating_3M', 
    'rs_rating_6m': 'RS_Rating_6M', 'sector': 'Sector', 'industry': 'Industry',
    'market_cap': 'Market_Cap', 'stage': 'Stage',
    'avg_mom': 'Avg_Mom', 'count': 'count'
}

def _map_row(row):
    return {COL_MAP.get(k.lower(), k): v for k, v in dict(row).items()}

def fetch_all(sql: str, params: Tuple = ()) -> List[dict]:
    """Execute a SELECT query and return all rows as a list of dicts."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            if DATABASE_URL and DATABASE_URL.startswith("postgres"):
                sql = sql.replace('?', '%s')
            cursor.execute(sql, params)
            return [_map_row(row) for row in cursor.fetchall()]
    except Exception as e:
        err_str = str(e).lower()
        if "does not exist" in err_str or "no such table" in err_str:
            print(f"Warning: Table missing (migration pending?), returning empty list. SQL: {sql[:50]}... Error: {e}", flush=True)
            return []
        raise

def fetch_one(sql: str, params: Tuple = ()) -> Optional[dict]:
    """Execute a SELECT query and return a single row as a dict."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            if DATABASE_URL and DATABASE_URL.startswith("postgres"):
                sql = sql.replace('?', '%s')
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return _map_row(row) if row else None
    except Exception as e:
        err_str = str(e).lower()
        if "does not exist" in err_str or "no such table" in err_str:
            print(f"Warning: Table missing (migration pending?), returning None. SQL: {sql[:50]}... Error: {e}", flush=True)
            return None
        raise


def get_last_updated(market: str = "US") -> Optional[str]:
    """Returns the most recent data date from the screen_data table."""
    try:
        result = fetch_one("SELECT MAX(Date) as last_date FROM screen_data WHERE Market = ?", (market,))
        return result.get("last_date") if result else None
    except Exception:
        return None  # Handle empty fresh database

def fetch_val(sql: str, params: Tuple = ()) -> Any:
    """Execute a SELECT query and return a single scalar value (e.g., COUNT(*))."""
    row = fetch_one(sql, params)
    if not row:
        return None
    # Extract the first column value dynamically robust against both dict and sqlite.Row
    return list(row.values())[0] if isinstance(row, dict) else tuple(row)[0]


def get_universe_count_in_db(market: str = "US") -> int:
    """Returns the total number of tickers in the database."""
    try:
        result = fetch_one("SELECT COUNT(*) as cnt FROM screen_data WHERE Market = ?", (market,))
        return result.get("cnt", 0) if result else 0
    except Exception:
        return 0
