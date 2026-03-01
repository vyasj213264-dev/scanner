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
        return magic_service.get_magic_test_data()
    except Exception as e:
        # Self-healing: try to init tables if they are missing
        if "does not exist" in str(e) or "no such table" in str(e):
            from api.services.auth_service import init_user_tables
            try:
                init_user_tables()
                return magic_service.get_magic_test_data()
            except Exception as e2:
                raise HTTPException(status_code=500, detail=f"Migration failed: {str(e2)}")
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
