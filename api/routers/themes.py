from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
import traceback
from api.models.themes import ThemeResponse
from api.models.scanner import ScanResponse, StockResult
from api.services.theme_service import get_themes, get_themes_stocks

router = APIRouter(prefix="/api/v1", tags=["Themes"])

@router.get(
    "/themes",
    response_model=ThemeResponse,
    summary="Get Industry and Sector Theme Ranks",
)
def fetch_themes(market: str = Query("US", description="US or IN")):
    """
    Returns the comprehensive rankings for all market sectors and industries 
    across 6 timeframes (1D, 1W, 1M, 3M, 6M, 1Y). 
    Includes real-time rank momentum and sector→industry mapping for drill-down.
    """
    try:
        results, last_updated, sector_map = get_themes(market=market.upper())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{exc}\n{traceback.format_exc()}")

    return ThemeResponse(
        as_of_date=last_updated,
        data=results,
        sector_industry_map=sector_map,
    )


@router.get(
    "/themes/stocks",
    response_model=ScanResponse,
    summary="Get stocks in a specific Sector or Industry",
)
def fetch_theme_stocks(
    category: str = Query(..., description="'Sector' or 'Industry'"),
    name: str = Query(..., description="Name of the sector or industry"),
    min_market_cap: Optional[float] = Query(None, description="Minimum market cap filter"),
    min_adr: Optional[float] = Query(None, description="Minimum ADR% filter"),
    max_adr: Optional[float] = Query(None, description="Maximum ADR% filter"),
    min_price: Optional[float] = Query(None, description="Minimum price filter"),
    market: str = Query("US", description="US or IN"),
):
    """
    Returns all stocks belonging to a given Sector or Industry,
    with full indicator data for chart rendering.
    """
    try:
        rows, universe, last_updated = get_themes_stocks(
            category,
            name,
            min_market_cap=min_market_cap,
            min_adr=min_adr,
            max_adr=max_adr,
            min_price=min_price,
            market=market.upper()
        )
        results = [StockResult.model_validate(row) for row in rows]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{exc}\n{traceback.format_exc()}")

    return ScanResponse(
        scanner=f"{category.lower()}-{name.lower().replace(' ', '-')}",
        label=name,
        category=category,
        count=len(results),
        total_universe=universe,
        as_of_date=last_updated,
        data=results,
    )

@router.get(
    "/themes/custom_indices",
    response_model=ThemeResponse,
    summary="Get Custom Index Theme Ranks (Indian Market)",
)
def fetch_custom_index_themes(market: str = Query("IN", description="US or IN")):
    """
    Returns the comprehensive rankings for Indian Market Custom Indices
    across 6 timeframes (1D, 1W, 1M, 3M, 6M, 1Y).
    Calculated dynamically from constituent momentum in screen_data.
    """
    from api.services.theme_service import get_custom_index_themes
    try:
        results, last_updated = get_custom_index_themes(market=market.upper())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{exc}\n{traceback.format_exc()}")

    return ThemeResponse(
        as_of_date=last_updated,
        data=results,
        sector_industry_map={},
    )


@router.get(
    "/themes/custom_indices/stocks",
    response_model=ScanResponse,
    summary="Get stocks in a specific Custom Index",
)
def fetch_custom_index_stocks(
    idx_id: str = Query(..., description="ID of the Custom Index (e.g., PCI:AGROCHEMDOM)"),
    market: str = Query("IN", description="US or IN"),
):
    """
    Returns all constituent stocks belonging to a given Custom Index,
    with full indicator data for chart rendering.
    """
    import os
    import json
    from api.database import fetch_all, fetch_val
    try:
        path = os.path.join(os.path.dirname(__file__), '..', 'custom_indices_in.json')
        if not os.path.exists(path) or market.upper() != "IN":
            raise HTTPException(status_code=404, detail="Custom Indices only available for IN market")
            
        with open(path, 'r') as f:
            custom_indices = json.load(f)
            
        if idx_id not in custom_indices:
            raise HTTPException(status_code=404, detail="Custom Index not found")
            
        info = custom_indices[idx_id]
        name = info.get('name', idx_id)
        constituents = info.get('constituents', [])
        
        if not constituents:
            rows = []
        else:
            placeholders = ','.join(['?']*len(constituents))
            query = f"SELECT * FROM screen_data WHERE Market = ? AND Ticker IN ({placeholders}) ORDER BY RS_Rating DESC NULLS LAST"
            params = [market.upper()] + constituents
            
            # Accommodate postgres vs sqlite params (sqlite uses ?, postgres uses %s)
            from api.database import get_db
            with get_db() as db:
                is_postgres = hasattr(db, 'dsn') or (hasattr(db, 'info') and getattr(db, 'info', None) is not None)
                if is_postgres:
                    query = f"SELECT * FROM screen_data WHERE Market = %s AND Ticker IN ({','.join(['%s']*len(constituents))}) ORDER BY RS_Rating DESC NULLS LAST"
            
            rows = fetch_all(query, tuple(params))
            
        results = [StockResult.model_validate(row) for row in rows]
        universe = fetch_val(f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market.upper()}'") or 0
        last_updated_row = fetch_all(f"SELECT MAX(Date) as last_date FROM screen_data WHERE Market = '{market.upper()}'")
        last_updated = last_updated_row[0].get('last_date', last_updated_row[0].get('max')) if last_updated_row else "Unknown"
        
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{exc}\n{traceback.format_exc()}")

    return ScanResponse(
        scanner=f"custom-index-{idx_id}",
        label=name,
        category="Custom Index",
        count=len(results),
        total_universe=universe,
        as_of_date=last_updated,
        data=results,
    )


@router.get(
    "/themes/proxy",
    response_model=List[str],
    summary="Get highly liquid proxy stocks for an Industry or Sector",
)
def fetch_theme_proxy(
    category: str = Query(..., description="'Sector' or 'Industry'"),
    name: str = Query(..., description="Name of the sector or industry"),
    limit: int = Query(10, description="Max number of proxy stocks"),
    market: str = Query("US", description="US or IN"),
):
    from api.services.theme_service import get_theme_proxies
    try:
        tickers = get_theme_proxies(category, name, limit, market=market.upper())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{exc}\n{traceback.format_exc()}")
    
    return tickers
