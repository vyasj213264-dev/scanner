"""
Scanner router — GET /api/v1/scan/{scanner_type}
              — GET /api/v1/scanners
              — GET /api/v1/stock/{ticker}
"""
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Query

from api.models.scanner import ScanResponse, ScannerCatalogueResponse, UniverseResponse, UniverseStockResult, StockResult
from api.services.scanner_service import (
    SCANNER_CATALOGUE,
    get_scanner_meta,
    run_scan,
    get_universe
)
from api.services import scanner_service
from api.config import DEFAULT_SCAN_LIMIT, MAX_SCAN_LIMIT
from api.database import fetch_all

router = APIRouter(prefix="/api/v1", tags=["Scanner"])


@router.get(
    "/stock/{ticker}",
    response_model=StockResult,
    summary="Get full metrics for a single ticker",
)
def get_stock_detail(ticker: str):
    """Returns all available metrics for a single stock ticker."""
    rows = fetch_all(
        "SELECT * FROM screen_data WHERE Ticker = ? LIMIT 1",
        (ticker.upper(),),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")
    return StockResult.model_validate(rows[0])


@router.get(
    "/scanners",
    response_model=ScannerCatalogueResponse,
    summary="List all available scanners",
)
def list_scanners():
    """Returns the full catalogue of scanner IDs, labels, descriptions, and categories."""
    return ScannerCatalogueResponse(scanners=SCANNER_CATALOGUE)


@router.get(
    "/universe",
    response_model=UniverseResponse,
    summary="Get full universe performance data",
)
def get_full_universe(
    min_market_cap: Optional[float] = Query(None, description="Minimum market cap filter"),
    min_adr: Optional[float] = Query(None, description="Minimum ADR% filter"),
    max_adr: Optional[float] = Query(None, description="Maximum ADR% filter"),
    min_price: Optional[float] = Query(None, description="Minimum price filter"),
    include_sectors: Optional[List[str]] = Query(None, description="Sectors to include"),
    exclude_sectors: Optional[List[str]] = Query(None, description="Sectors to exclude"),
    include_industries: Optional[List[str]] = Query(None, description="Industries to include"),
    exclude_industries: Optional[List[str]] = Query(None, description="Industries to exclude"),
):
    """Returns the performance metrics for the entire market universe > $5, with optional filters."""
    try:
        rows, universe_count, last_updated = get_universe(
            min_market_cap=min_market_cap,
            min_adr=min_adr,
            max_adr=max_adr,
            min_price=min_price,
            include_sectors=include_sectors,
            exclude_sectors=exclude_sectors,
            include_industries=include_industries,
            exclude_industries=exclude_industries,
        )
        results = [UniverseStockResult.model_validate(row) for row in rows]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return UniverseResponse(
        total_universe=universe_count,
        as_of_date=last_updated,
        data=results,
    )


@router.get(
    "/scan/{scanner_type}",
    response_model=ScanResponse,
    summary="Run a predefined stock scanner",
)
def run_scanner(
    scanner_type: str,
    limit: int = Query(DEFAULT_SCAN_LIMIT, ge=1, le=MAX_SCAN_LIMIT, description="Max results to return"),
    sort_by: Literal["rs_rating", "rvol", "close", "pct_from_52w_high", "momentum_1m"] = Query(
        "rs_rating", description="Field to sort by"
    ),
    order: Literal["asc", "desc"] = Query("desc", description="Sort direction"),
    min_market_cap: Optional[float] = Query(None, description="Minimum market cap filter"),
    min_adr: Optional[float] = Query(None, description="Minimum ADR% filter"),
    max_adr: Optional[float] = Query(None, description="Maximum ADR% filter"),
    min_price: Optional[float] = Query(None, description="Minimum price filter"),
    include_sectors: Optional[List[str]] = Query(None, description="Sectors to include"),
    exclude_sectors: Optional[List[str]] = Query(None, description="Sectors to exclude"),
    include_industries: Optional[List[str]] = Query(None, description="Industries to include"),
    exclude_industries: Optional[List[str]] = Query(None, description="Industries to exclude"),
):
    """
    Execute a predefined scanner and return matching stocks with their indicator data.

    Available scanner types are listed at `/api/v1/scanners`.
    """
    meta = get_scanner_meta(scanner_type)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scanner '{scanner_type}' not found. Call /api/v1/scanners for valid IDs.",
        )

    try:
        results, universe, last_updated = run_scan(
            scanner_id=scanner_type,
            limit=limit,
            sort_by=sort_by,
            order=order,
            min_market_cap=min_market_cap,
            min_adr=min_adr,
            max_adr=max_adr,
            min_price=min_price,
            include_sectors=include_sectors,
            exclude_sectors=exclude_sectors,
            include_industries=include_industries,
            exclude_industries=exclude_industries,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ScanResponse(
        scanner=scanner_type,
        label=meta.label,
        category=meta.category,
        count=len(results),
        total_universe=universe,
        as_of_date=last_updated,
        data=results,
    )
