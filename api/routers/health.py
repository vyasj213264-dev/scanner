"""
Health check router — GET /api/v1/health
"""
from fastapi import APIRouter, Query

from api.database import get_universe_count_in_db, get_last_updated
from api.models.scanner import HealthResponse
from api.config import APP_VERSION

router = APIRouter(prefix="/api/v1", tags=["System"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def health_check(market: str = Query("US", description="US or IN context")):
    """Returns DB connectivity, universe size, last data update timestamp, and macro health."""
    from api.database import fetch_one
    macro_health = None
    try:
        universe_size = get_universe_count_in_db(market)
        last_updated = get_last_updated(market)
        db_ok = universe_size > 0
        
        # Kell-Zanger Macro Health Check
        benchmark = "SPY" if market == "US" else "^NSEI"
        row = fetch_one(
            "SELECT Close, EMA_21, SMA_50, SMA_200 FROM screen_data WHERE Ticker = ? AND Market = ?",
            (benchmark, market)
        )
        if row and row.get('Close') and row.get('EMA_21') and row.get('SMA_50') and row.get('SMA_200'):
            cl = float(row['Close'])
            ema21 = float(row['EMA_21'])
            sma50 = float(row['SMA_50'])
            sma200 = float(row['SMA_200'])
            
            trend_up = cl > ema21
            struct_up = sma50 > sma200
            
            if trend_up and struct_up:
                macro_health = "Green"
            elif not trend_up and not struct_up:
                macro_health = "Red"
            else:
                macro_health = "Yellow"
                
    except Exception:
        universe_size = 0
        last_updated = None
        db_ok = False

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db_ok=db_ok,
        universe_size=universe_size,
        last_updated=last_updated,
        version=APP_VERSION,
        macro_health=macro_health,
    )
