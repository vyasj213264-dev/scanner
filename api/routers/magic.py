"""
Magic router — Public endpoints for the /test page.
"""
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from api.services import magic_service

router = APIRouter(prefix="/api/v1/magic", tags=["Magic"])

class WatchlistSection(BaseModel):
    section: str
    tickers: List[str]

@router.get("/test", summary="Get sectioned magic watchlist data with live metrics")
def get_magic_test():
    """Returns grouped stocks for the public /test page."""
    try:
        data = magic_service.get_magic_test_data()
        if not data:
            # If database is empty, trigger a sync directly
            magic_service.sync_tradingview_watchlist()
            data = magic_service.get_magic_test_data()
        return data
    except Exception as e:
        # Self-healing: try to init tables if they are missing
        err_str = str(e).lower()
        if "does not exist" in err_str or "no such table" in err_str:
            from api.database import get_db, DATABASE_URL
            is_postgres = DATABASE_URL and DATABASE_URL.startswith("postgres")
            pk_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
            now_func = "DEFAULT CURRENT_TIMESTAMP" if is_postgres else "DEFAULT (datetime('now'))"
            
            try:
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute(f"""
                        CREATE TABLE IF NOT EXISTS magic_watchlist_items (
                            id          {pk_type},
                            section     TEXT NOT NULL,
                            ticker      TEXT NOT NULL,
                            sort_order  INTEGER DEFAULT 0,
                            updated_at  TIMESTAMP {now_func}
                        );
                    """)
                    conn.commit()
                # Now that table exists, sync and return
                magic_service.sync_tradingview_watchlist()
                return magic_service.get_magic_test_data()
            except Exception as e2:
                raise HTTPException(status_code=500, detail=f"Self-healing failed: {str(e2)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test", summary="Overwrite magic watchlist data")
def update_magic_test(payload: List[WatchlistSection]):
    """Overwrites the magic watchlist. Payload: [{'section': '...', 'tickers': [...]}]"""
    try:
        # Convert Pydantic models to dicts
        raw_payload = [item.model_dump() for item in payload]
        magic_service.update_magic_test_data(raw_payload)
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
