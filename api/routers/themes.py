from typing import List
from fastapi import APIRouter, HTTPException, Query
from api.models.themes import ThemeResponse
from api.models.scanner import ScanResponse, StockResult
from api.services.theme_service import get_themes, get_themes_stocks

router = APIRouter(prefix="/api/v1", tags=["Themes"])

@router.get(
    "/themes",
    response_model=ThemeResponse,
    summary="Get Industry and Sector Theme Ranks",
)
def fetch_themes():
    """
    Returns the comprehensive rankings for all market sectors and industries 
    across 6 timeframes (1D, 1W, 1M, 3M, 6M, 1Y). 
    Includes real-time rank momentum and sector→industry mapping for drill-down.
    """
    try:
        results, last_updated, sector_map = get_themes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

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
):
    """
    Returns all stocks belonging to a given Sector or Industry,
    with full indicator data for chart rendering.
    """
    try:
        rows, universe, last_updated = get_themes_stocks(category, name)
        results = [StockResult.model_validate(row) for row in rows]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

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
    "/themes/proxy",
    response_model=List[str],
    summary="Get highly liquid proxy stocks for an Industry or Sector",
)
def fetch_theme_proxies(
    category: str = Query(..., description="'Sector' or 'Industry'"),
    name: str = Query(..., description="Name of the sector or industry"),
    limit: int = Query(10, description="Max number of tickers to return"),
):
    """
    Returns a list of ticker symbols that are the most heavily weighted
    or liquid in a given category. Used for dynamically building 
    TradingView expression charts for unmapped industries.
    """
    from api.services.theme_service import get_theme_proxies
    try:
        tickers = get_theme_proxies(category, name, limit)
        return tickers
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
