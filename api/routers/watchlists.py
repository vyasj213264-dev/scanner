"""
Watchlists router — CRUD for user watchlists and their stocks.
All routes require authentication.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
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
    created_at: Optional[str] = None

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
    return watchlist_service.create_watchlist(user.id, body.name.strip())


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
def get_watchlist_stocks(watchlist_id: int, user: User = Depends(require_user)):
    rows = watchlist_service.get_watchlist_stocks(watchlist_id, user.id)
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
