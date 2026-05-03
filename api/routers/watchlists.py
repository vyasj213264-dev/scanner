"""
Watchlists router — CRUD for user watchlists and their stocks.
All routes require authentication.
"""
from datetime import datetime
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from api.models.user import User
from api.routers.auth import require_user
from api.services import watchlist_service
from api.services.scanner_service import BASELINE_FILTER
from api.models.scanner import StockResult

router = APIRouter(prefix="/api/v1/watchlists", tags=["Watchlists"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class WatchlistCreate(BaseModel):
    name: str

class WatchlistRename(BaseModel):
    name: str

class AddStockRequest(BaseModel):
    ticker: str

class WatchlistOut(BaseModel):
    id: int
    name: str
    created_at: Optional[Union[str, datetime]] = None

class WatchlistStocksResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    watchlist_id: int
    watchlist_name: str
    data: List[StockResult]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[WatchlistOut], summary="List current user's watchlists")
def list_watchlists(user: User = Depends(require_user)):
    return watchlist_service.get_watchlists(user.id)


@router.post("", response_model=WatchlistOut, summary="Create a new watchlist")
def create_watchlist(body: WatchlistCreate, user: User = Depends(require_user)):
    name = body.name.strip()
    existing = watchlist_service.get_watchlists(user.id)
    if any(w["name"].lower() == name.lower() for w in existing):
        raise HTTPException(status_code=400, detail="A watchlist with this name already exists")
    return watchlist_service.create_watchlist(user.id, name)


@router.patch("/{watchlist_id}", response_model=WatchlistOut, summary="Rename a watchlist")
def rename_watchlist(watchlist_id: int, body: WatchlistRename, user: User = Depends(require_user)):
    ok = watchlist_service.rename_watchlist(watchlist_id, user.id, body.name.strip())
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    lists = watchlist_service.get_watchlists(user.id)
    return next((w for w in lists if w["id"] == watchlist_id), None)


@router.delete("/{watchlist_id}", summary="Delete a watchlist")
def delete_watchlist(watchlist_id: int, user: User = Depends(require_user)):
    ok = watchlist_service.delete_watchlist(watchlist_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return {"deleted": watchlist_id}


@router.get("/{watchlist_id}/stocks", summary="Get all stocks in a watchlist with live metrics")
def get_watchlist_stocks(
    watchlist_id: int,
    min_market_cap: Optional[float] = None,
    min_adr: Optional[float] = None,
    max_adr: Optional[float] = None,
    min_price: Optional[float] = None,
    include_sectors: Optional[List[str]] = Query(None),
    exclude_sectors: Optional[List[str]] = Query(None),
    include_industries: Optional[List[str]] = Query(None),
    exclude_industries: Optional[List[str]] = Query(None),
    user: User = Depends(require_user)
):
    rows = watchlist_service.get_watchlist_stocks(
        watchlist_id, 
        user.id,
        min_market_cap=min_market_cap,
        min_adr=min_adr,
        max_adr=max_adr,
        min_price=min_price,
        include_sectors=include_sectors,
        exclude_sectors=exclude_sectors,
        include_industries=include_industries,
        exclude_industries=exclude_industries,
    )
    if rows is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    results = [StockResult.model_validate(r) for r in rows if r.get("Ticker")]
    lists = watchlist_service.get_watchlists(user.id)
    wl_name = next((w["name"] for w in lists if w["id"] == watchlist_id), "Watchlist")
    return {"watchlist_id": watchlist_id, "watchlist_name": wl_name, "count": len(results), "data": results}


@router.post("/{watchlist_id}/stocks", summary="Add a ticker to a watchlist")
def add_stock(watchlist_id: int, body: AddStockRequest, user: User = Depends(require_user)):
    ok = watchlist_service.add_stock_to_watchlist(watchlist_id, user.id, body.ticker)
    if not ok:
        raise HTTPException(status_code=400, detail="Already in watchlist or watchlist not found")
    return {"added": body.ticker.upper()}


@router.delete("/{watchlist_id}/stocks/{ticker}", summary="Remove a ticker from a watchlist")
def remove_stock(watchlist_id: int, ticker: str, user: User = Depends(require_user)):
    ok = watchlist_service.remove_stock_from_watchlist(watchlist_id, user.id, ticker)
    if not ok:
        raise HTTPException(status_code=404, detail="Stock or watchlist not found")
    return {"removed": ticker.upper()}
@router.get("/debug/migrate", summary="Force migration and debug")
def debug_migrate_watchlists():
    import traceback
    from api.database import get_user_db, get_db
    from api.config import DATABASE_URL
    is_postgres = DATABASE_URL and DATABASE_URL.startswith("postgres")
    
    logs = []
    try:
        with get_user_db() as conn:
            cursor = conn.cursor()
            
            # Create table just in case it rolled back
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watchlist_portfolio (
                    id            SERIAL PRIMARY KEY,
                    watchlist_id  INTEGER NOT NULL,
                    ticker        TEXT NOT NULL,
                    entry_date    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    entry_price   REAL,
                    exit_date     TIMESTAMP,
                    exit_price    REAL,
                    status        TEXT DEFAULT 'ACTIVE'
                );
            """ if is_postgres else """
                CREATE TABLE IF NOT EXISTS watchlist_portfolio (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    watchlist_id  INTEGER NOT NULL,
                    ticker        TEXT NOT NULL,
                    entry_date    TIMESTAMP DEFAULT (datetime('now')),
                    entry_price   REAL,
                    exit_date     TIMESTAMP,
                    exit_price    REAL,
                    status        TEXT DEFAULT 'ACTIVE',
                    FOREIGN KEY (watchlist_id) REFERENCES watchlists(id)
                );
            """)
            conn.commit()
            logs.append("Table verified/created.")
            
            cursor.execute("""
                SELECT ws.watchlist_id, ws.ticker, ws.added_at 
                FROM watchlist_stocks ws
                LEFT JOIN watchlist_portfolio wp 
                  ON ws.watchlist_id = wp.watchlist_id AND ws.ticker = wp.ticker
                WHERE wp.id IS NULL
            """)
            old_stocks = cursor.fetchall()
            logs.append(f"Found {len(old_stocks)} missing stocks.")
            
            if len(old_stocks) > 0:
                # Fetch prices
                prices = {}
                try:
                    with get_db() as scan_conn:
                        sc = scan_conn.cursor()
                        sc.execute("SELECT Ticker, Close FROM screen_data")
                        for r in sc.fetchall():
                            if isinstance(r, dict):
                                prices[r['Ticker']] = r['Close']
                            elif hasattr(r, 'keys'): # DictRow
                                prices[dict(r)['Ticker']] = dict(r)['Close']
                            else:
                                prices[r[0]] = r[1]
                except Exception as e:
                    logs.append(f"Could not fetch prices: {e}")
                
                success = 0
                for row in old_stocks:
                    try:
                        if isinstance(row, dict):
                            r_dict = row
                        elif hasattr(row, 'keys'):
                            r_dict = dict(row)
                        else:
                            # In sqlite, row factory makes it behave like dict, but if not:
                            r_dict = {'watchlist_id': row[0], 'ticker': row[1]}
                            
                        wid = r_dict['watchlist_id']
                        tick = r_dict['ticker']
                        price = prices.get(tick)
                        
                        if is_postgres:
                            cursor.execute("INSERT INTO watchlist_portfolio (watchlist_id, ticker, entry_date, entry_price, status) VALUES (%s, %s, %s, %s, 'ACTIVE')", (wid, tick, '2026-05-01 00:00:00', price))
                        else:
                            cursor.execute("INSERT INTO watchlist_portfolio (watchlist_id, ticker, entry_date, entry_price, status) VALUES (?, ?, ?, ?, 'ACTIVE')", (wid, tick, '2026-05-01 00:00:00', price))
                        
                        conn.commit() # Commit each one so a single failure doesn't rollback all
                        success += 1
                    except Exception as e:
                        conn.rollback()
                        logs.append(f"Failed to migrate {tick}: {e}")
                
                logs.append(f"Successfully migrated {success} stocks.")
            
    except Exception as e:
        logs.append(f"Fatal error: {e}\n{traceback.format_exc()}")
        
    return {"status": "done", "logs": logs}

@router.get("/debug/fix-dates", summary="Fix entry dates to April 30")
def debug_fix_dates():
    from api.database import get_user_db
    from api.config import DATABASE_URL
    is_postgres = DATABASE_URL and DATABASE_URL.startswith("postgres")
    
    logs = []
    try:
        with get_user_db() as conn:
            cursor = conn.cursor()
            if is_postgres:
                cursor.execute("UPDATE watchlist_portfolio SET entry_date = %s WHERE entry_date = %s", ('2026-04-30 00:00:00', '2026-05-01 00:00:00'))
            else:
                cursor.execute("UPDATE watchlist_portfolio SET entry_date = ? WHERE entry_date = ?", ('2026-04-30 00:00:00', '2026-05-01 00:00:00'))
            conn.commit()
            logs.append(f"Updated {cursor.rowcount} entries from May 1 to April 30.")
    except Exception as e:
        logs.append(f"Error: {e}")
    
    return {"status": "done", "logs": logs}

@router.get("/debug/backfill-prices", summary="Backfill null entry prices")
def debug_backfill_prices():
    import traceback
    from api.database import get_user_db, get_db
    from api.config import DATABASE_URL
    is_postgres = DATABASE_URL and DATABASE_URL.startswith("postgres")
    
    logs = []
    try:
        # Step 1: Get all portfolio entries with null entry_price
        with get_user_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, ticker FROM watchlist_portfolio WHERE entry_price IS NULL AND status = 'ACTIVE'")
            null_rows = cursor.fetchall()
            logs.append(f"Found {len(null_rows)} entries with null entry_price.")
        
        if len(null_rows) == 0:
            return {"status": "done", "logs": logs}
        
        # Step 2: Fetch prices from screen_data (case-safe)
        prices = {}
        try:
            with get_db() as scan_conn:
                sc = scan_conn.cursor()
                sc.execute("SELECT * FROM screen_data LIMIT 1")
                sample = sc.fetchone()
                if sample:
                    cols = list(dict(sample).keys())
                    logs.append(f"screen_data columns sample: {cols[:10]}")
                    # Find the right column names
                    ticker_col = next((c for c in cols if c.lower() == 'ticker'), None)
                    close_col = next((c for c in cols if c.lower() == 'close'), None)
                    logs.append(f"Using ticker_col={ticker_col}, close_col={close_col}")
                    
                    if ticker_col and close_col:
                        sc.execute(f'SELECT "{ticker_col}", "{close_col}" FROM screen_data')
                        for r in sc.fetchall():
                            rd = dict(r)
                            prices[rd[ticker_col]] = rd[close_col]
                        logs.append(f"Fetched prices for {len(prices)} tickers.")
        except Exception as e:
            logs.append(f"Price fetch error: {e}")
        
        # Step 3: Update
        updated = 0
        with get_user_db() as conn:
            cursor = conn.cursor()
            for row in null_rows:
                rd = dict(row)
                pid = rd['id']
                tick = rd['ticker']
                price = prices.get(tick)
                if price is not None:
                    if is_postgres:
                        cursor.execute("UPDATE watchlist_portfolio SET entry_price = %s WHERE id = %s", (price, pid))
                    else:
                        cursor.execute("UPDATE watchlist_portfolio SET entry_price = ? WHERE id = ?", (price, pid))
                    updated += 1
            conn.commit()
        logs.append(f"Updated {updated} entries with prices.")
        
    except Exception as e:
        logs.append(f"Error: {e}\n{traceback.format_exc()}")
    
    return {"status": "done", "logs": logs}
