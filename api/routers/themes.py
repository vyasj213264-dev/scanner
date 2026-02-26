from fastapi import APIRouter, HTTPException
from api.models.themes import ThemeResponse
from api.services.theme_service import get_themes

router = APIRouter(prefix="/api/v1", tags=["Themes"])

@router.get(
    "/themes",
    response_model=ThemeResponse,
    summary="Get Industry and Sector Theme Ranks",
)
def fetch_themes():
    """
    Returns the comprehensive 1-73 rankings for all market sectors and industries 
    across 6 timeframes (1D, 1W, 1M, 3M, 6M, 1Y). 
    Includes real-time rank momentum (+ or -) compared against the previous trading day.
    """
    try:
        results, last_updated = get_themes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ThemeResponse(
        as_of_date=last_updated,
        data=results,
    )
