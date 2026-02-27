"""
Market Breadth router — GET /api/v1/breadth
Computes breadth metrics from screen_data in real time.
"""
from fastapi import APIRouter
from api.database import fetch_all, fetch_val

router = APIRouter(prefix="/api/v1", tags=["Market Breadth"])


@router.get("/breadth", summary="Get market breadth indicators")
def get_breadth():
    """
    Returns market-wide and sector-level breadth indicators computed from screen_data.
    """
    total = fetch_val("SELECT COUNT(*) FROM screen_data WHERE Close >= 5") or 1

    def pct(val):
        return round((val / total) * 100, 1) if total > 0 else 0

    above_50 = fetch_val(
        "SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND SMA_50 IS NOT NULL AND Close > SMA_50"
    ) or 0
    above_200 = fetch_val(
        "SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND SMA_200 IS NOT NULL AND Close > SMA_200"
    ) or 0
    stage2 = fetch_val(
        "SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND In_Stage_2 = 1"
    ) or 0
    pos_1m = fetch_val(
        "SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND Momentum_1M > 0"
    ) or 0
    pos_3m = fetch_val(
        "SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND Momentum_3M > 0"
    ) or 0
    pos_6m = fetch_val(
        "SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND Momentum_6M > 0"
    ) or 0
    # New highs: within 5% of 52W high proxy (pct_from_52w_high > -5)
    near_highs = fetch_val(
        "SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND Pct_From_52W_High >= -5"
    ) or 0
    near_lows = fetch_val(
        "SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND Pct_From_52W_High <= -40"
    ) or 0

    # Sector-level breakdown
    sector_rows = fetch_all(
        """
        SELECT 
            Sector,
            COUNT(*) as total,
            SUM(CASE WHEN Close > SMA_50 THEN 1 ELSE 0 END) as above_50sma,
            SUM(CASE WHEN Close > SMA_200 THEN 1 ELSE 0 END) as above_200sma,
            SUM(CASE WHEN In_Stage_2 = 1 THEN 1 ELSE 0 END) as stage2_count,
            SUM(CASE WHEN Momentum_1M > 0 THEN 1 ELSE 0 END) as pos_1m,
            AVG(RS_Rating) as avg_rs
        FROM screen_data
        WHERE Close >= 5 AND Sector IS NOT NULL AND Sector != ''
        GROUP BY Sector
        ORDER BY avg_rs DESC
        """
    )

    sectors = []
    for r in sector_rows:
        t = r.get("total") or 1
        sectors.append({
            "sector": r.get("Sector") or r.get("sector"),
            "total": t,
            "pct_above_50sma": round((r.get("above_50sma") or 0) / t * 100, 1),
            "pct_above_200sma": round((r.get("above_200sma") or 0) / t * 100, 1),
            "pct_stage2": round((r.get("stage2_count") or 0) / t * 100, 1),
            "pct_pos_1m": round((r.get("pos_1m") or 0) / t * 100, 1),
            "avg_rs": round(r.get("avg_rs") or 0, 1),
        })

    return {
        "total_stocks": total,
        "pct_above_50sma": pct(above_50),
        "pct_above_200sma": pct(above_200),
        "pct_stage2": pct(stage2),
        "pct_pos_1m": pct(pos_1m),
        "pct_pos_3m": pct(pos_3m),
        "pct_pos_6m": pct(pos_6m),
        "near_highs": near_highs,
        "near_lows": near_lows,
        "sectors": sectors,
    }
