"""
Health check router — GET /api/v1/health
"""
from fastapi import APIRouter

from api.database import get_universe_count_in_db, get_last_updated
from api.models.scanner import HealthResponse
from api.config import APP_VERSION

router = APIRouter(prefix="/api/v1", tags=["System"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def health_check():
    """Returns DB connectivity, universe size, and last data update timestamp."""
    try:
        universe_size = get_universe_count_in_db()
        last_updated = get_last_updated()
        db_ok = universe_size > 0
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
    )
