"""
Market Breadth router — GET /api/v1/breadth
Computes breadth metrics from screen_data in real time.
"""
from fastapi import APIRouter, HTTPException
from api.database import fetch_all, fetch_val

router = APIRouter(prefix="/api/v1", tags=["Market Breadth"])


@router.get("/breadth", summary="Get market breadth indicators")
def get_breadth():
    """
    Returns market-wide and sector-level breadth indicators computed from screen_data.
    """
    try:
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
            "SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND In_Stage_2"
        ) or 0
        
        # New: Stan Weinstein 50-day SMA Stages
        stage1_count = fetch_val("SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND Stage = 1") or 0
        stage2_count = fetch_val("SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND Stage = 2") or 0
        stage3_count = fetch_val("SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND Stage = 3") or 0
        stage4_count = fetch_val("SELECT COUNT(*) FROM screen_data WHERE Close >= 5 AND Stage = 4") or 0
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
                SUM(CASE WHEN In_Stage_2 THEN 1 ELSE 0 END) as stage2_count_legacy,
                SUM(CASE WHEN Momentum_1M > 0 THEN 1 ELSE 0 END) as pos_1m,
                SUM(CASE WHEN Stage = 1 THEN 1 ELSE 0 END) as sw_stage1,
                SUM(CASE WHEN Stage = 2 THEN 1 ELSE 0 END) as sw_stage2,
                SUM(CASE WHEN Stage = 3 THEN 1 ELSE 0 END) as sw_stage3,
                SUM(CASE WHEN Stage = 4 THEN 1 ELSE 0 END) as sw_stage4,
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
                "pct_stage2_legacy": round((r.get("stage2_count_legacy") or 0) / t * 100, 1),
                "pct_pos_1m": round((r.get("pos_1m") or 0) / t * 100, 1),
                "avg_rs": round(r.get("avg_rs") or 0, 1),
                "pct_stage1": round((r.get("sw_stage1") or 0) / t * 100, 1),
                "pct_stage2": round((r.get("sw_stage2") or 0) / t * 100, 1),
                "pct_stage3": round((r.get("sw_stage3") or 0) / t * 100, 1),
                "pct_stage4": round((r.get("sw_stage4") or 0) / t * 100, 1),
            })
            
        # Industry-level breakdown (for SW Stages only)
        industry_rows = fetch_all(
            """
            SELECT 
                Industry,
                COUNT(*) as total,
                SUM(CASE WHEN Stage = 1 THEN 1 ELSE 0 END) as sw_stage1,
                SUM(CASE WHEN Stage = 2 THEN 1 ELSE 0 END) as sw_stage2,
                SUM(CASE WHEN Stage = 3 THEN 1 ELSE 0 END) as sw_stage3,
                SUM(CASE WHEN Stage = 4 THEN 1 ELSE 0 END) as sw_stage4
            FROM screen_data
            WHERE Close >= 5 AND Industry IS NOT NULL AND Industry != ''
            GROUP BY Industry
            ORDER BY total DESC
            """
        )
        
        industries = []
        for r in industry_rows:
            t = r.get("total") or 1
            industries.append({
                "industry": r.get("Industry") or r.get("industry"),
                "total": t,
                "pct_stage1": round((r.get("sw_stage1") or 0) / t * 100, 1),
                "pct_stage2": round((r.get("sw_stage2") or 0) / t * 100, 1),
                "pct_stage3": round((r.get("sw_stage3") or 0) / t * 100, 1),
                "pct_stage4": round((r.get("sw_stage4") or 0) / t * 100, 1),
            })
            
        # Global Stage History
        history_rows = fetch_all(
            "SELECT Date, Stage_1, Stage_2, Stage_3, Stage_4 FROM market_breadth_history ORDER BY Date ASC"
        )
        history = []
        for r in history_rows:
            history.append({
                "date": r.get("Date") or r.get("date"),
                "stage1": r.get("Stage_1") or r.get("stage_1"),
                "stage2": r.get("Stage_2") or r.get("stage_2"),
                "stage3": r.get("Stage_3") or r.get("stage_3"),
                "stage4": r.get("Stage_4") or r.get("stage_4"),
            })

        return {
            "total_stocks": total,
            "pct_above_50sma": pct(above_50),
            "pct_above_200sma": pct(above_200),
            "pct_stage2": pct(stage2), # legacy
            "pct_pos_1m": pct(pos_1m),
            "pct_pos_3m": pct(pos_3m),
            "pct_pos_6m": pct(pos_6m),
            "near_highs": near_highs,
            "near_lows": near_lows,
            "sectors": sectors,
            "industries": industries,
            # Global SW Stages
            "sw_stage1_count": stage1_count,
            "sw_stage2_count": stage2_count,
            "sw_stage3_count": stage3_count,
            "sw_stage4_count": stage4_count,
            "pct_sw_stage1": pct(stage1_count),
            "pct_sw_stage2": pct(stage2_count),
            "pct_sw_stage3": pct(stage3_count),
            "pct_sw_stage4": pct(stage4_count),
            "history": history,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
