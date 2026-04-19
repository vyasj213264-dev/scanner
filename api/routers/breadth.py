"""
Market Breadth router — GET /api/v1/breadth
Computes breadth metrics from screen_data in real time.
"""
from fastapi import APIRouter, HTTPException, Query
from api.database import fetch_all, fetch_val

from api.routers.auth import require_user
from fastapi import Depends

router = APIRouter(prefix="/api/v1", tags=["Market Breadth"], dependencies=[Depends(require_user)])


@router.get("/breadth", summary="Get market breadth indicators")
def get_breadth(market: str = Query("US", description="US or IN")):
    """
    Returns market-wide and sector-level breadth indicators computed from screen_data,
    filtered by market (US or IN).
    """
    market = market.upper()
    # Indian stocks are priced in INR, so $5 filter doesn't apply
    price_filter = "Close >= 5" if market == "US" else "Close > 0"
    
    try:
        total = fetch_val(f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter}") or 1

        def pct(val):
            return round((val / total) * 100, 1) if total > 0 else 0

        above_50 = fetch_val(
            f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND SMA_50 IS NOT NULL AND Close > SMA_50"
        ) or 0
        above_200 = fetch_val(
            f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND SMA_200 IS NOT NULL AND Close > SMA_200"
        ) or 0
        stage2 = fetch_val(
            f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND In_Stage_2"
        ) or 0
        
        # New: Stan Weinstein 50-day SMA Stages
        stage1_count = fetch_val(f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND Stage = 1") or 0
        stage2_count = fetch_val(f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND Stage = 2") or 0
        stage3_count = fetch_val(f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND Stage = 3") or 0
        stage4_count = fetch_val(f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND Stage = 4") or 0
        pos_1m = fetch_val(
            f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND Momentum_1M > 0"
        ) or 0
        pos_3m = fetch_val(
            f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND Momentum_3M > 0"
        ) or 0
        pos_6m = fetch_val(
            f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND Momentum_6M > 0"
        ) or 0
        # New highs: within 5% of 52W high proxy (pct_from_52w_high > -5)
        near_highs = fetch_val(
            f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND Pct_From_52W_High >= -5"
        ) or 0
        near_lows = fetch_val(
            f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {price_filter} AND Pct_From_52W_High <= -40"
        ) or 0

        # Sector-level breakdown
        sector_rows = fetch_all(
            f"""
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
            WHERE Market = '{market}' AND {price_filter} AND Sector IS NOT NULL AND Sector != ''
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
            f"""
            SELECT 
                Industry,
                COUNT(*) as total,
                SUM(CASE WHEN Stage = 1 THEN 1 ELSE 0 END) as sw_stage1,
                SUM(CASE WHEN Stage = 2 THEN 1 ELSE 0 END) as sw_stage2,
                SUM(CASE WHEN Stage = 3 THEN 1 ELSE 0 END) as sw_stage3,
                SUM(CASE WHEN Stage = 4 THEN 1 ELSE 0 END) as sw_stage4
            FROM screen_data
            WHERE Market = '{market}' AND {price_filter} AND Industry IS NOT NULL AND Industry != ''
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
            
        # Global Stage History (filtered by market)
        history_rows = fetch_all(
            f"SELECT Date, Stage_1, Stage_2, Stage_3, Stage_4 FROM market_breadth_history WHERE Market = '{market}' ORDER BY Date ASC"
        )
        
        from datetime import datetime, timedelta
        six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        
        history = []
        for r in history_rows:
            date_str = r.get("Date") or r.get("date")
            if date_str and str(date_str) >= six_months_ago:
                history.append({
                    "date": date_str,
                    "stage1": r.get("Stage_1") or r.get("stage_1"),
                    "stage2": r.get("Stage_2") or r.get("stage_2"),
                    "stage3": r.get("Stage_3") or r.get("stage_3"),
                    "stage4": r.get("Stage_4") or r.get("stage_4"),
                })

        # ------- IBD ETF Rotation Data (US only) -------
        etf_rotation = None
        if market == "US":
            try:
                etf_latest_date = fetch_val("SELECT MAX(Date) FROM ibd_etf_ranks WHERE Market = 'US'")
                if etf_latest_date:
                    # Sector ETFs
                    sector_etf_rows = fetch_all(f"""
                        SELECT ETF_Ticker, ETF_Name, Sector,
                               Rank_1D, Rank_1W, Rank_1M, Rank_3M, Rank_6M, Rank_1Y,
                               Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y,
                               Pct_From_52W_High, Stage, Above_50DMA, Above_200DMA
                        FROM ibd_etf_ranks
                        WHERE Market = 'US' AND Date = '{etf_latest_date}' AND Tier = 'Sector'
                        ORDER BY Rank_3M ASC
                    """)
                    
                    # Industry ETFs — all, sorted by 3M rank
                    industry_etf_rows = fetch_all(f"""
                        SELECT ETF_Ticker, ETF_Name, Sector,
                               Rank_1D, Rank_1W, Rank_1M, Rank_3M, Rank_6M, Rank_1Y,
                               Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y,
                               Pct_From_52W_High, Stage, Above_50DMA, Above_200DMA
                        FROM ibd_etf_ranks
                        WHERE Market = 'US' AND Date = '{etf_latest_date}' AND Tier = 'Industry'
                        ORDER BY Rank_3M ASC
                    """)
                    
                    def _etf_row(r):
                        return {
                            "ticker": r.get("ETF_Ticker") or r.get("etf_ticker"),
                            "name": r.get("ETF_Name") or r.get("etf_name"),
                            "sector": r.get("Sector") or r.get("sector"),
                            "rank_1d": r.get("Rank_1D") or r.get("rank_1d"),
                            "rank_1w": r.get("Rank_1W") or r.get("rank_1w"),
                            "rank_1m": r.get("Rank_1M") or r.get("rank_1m"),
                            "rank_3m": r.get("Rank_3M") or r.get("rank_3m"),
                            "rank_6m": r.get("Rank_6M") or r.get("rank_6m"),
                            "rank_1y": r.get("Rank_1Y") or r.get("rank_1y"),
                            "momentum_1d": round(r.get("Momentum_1D") or r.get("momentum_1d") or 0, 2),
                            "momentum_1w": round(r.get("Momentum_1W") or r.get("momentum_1w") or 0, 2),
                            "momentum_1m": round(r.get("Momentum_1M") or r.get("momentum_1m") or 0, 2),
                            "momentum_3m": round(r.get("Momentum_3M") or r.get("momentum_3m") or 0, 2),
                            "momentum_6m": round(r.get("Momentum_6M") or r.get("momentum_6m") or 0, 2),
                            "momentum_1y": round(r.get("Momentum_1Y") or r.get("momentum_1y") or 0, 2),
                            "pct_from_high": round(r.get("Pct_From_52W_High") or r.get("pct_from_52w_high") or 0, 1),
                            "stage": r.get("Stage") or r.get("stage"),
                            "above_50dma": bool(r.get("Above_50DMA") or r.get("above_50dma")),
                            "above_200dma": bool(r.get("Above_200DMA") or r.get("above_200dma")),
                        }
                    
                    sector_etfs_data = [_etf_row(r) for r in sector_etf_rows]
                    all_industry_etfs = [_etf_row(r) for r in industry_etf_rows]
                    
                    total_ind = len(all_industry_etfs)
                    above_50_count = sum(1 for e in all_industry_etfs if e["above_50dma"])
                    above_200_count = sum(1 for e in all_industry_etfs if e["above_200dma"])
                    stage2_count_etf = sum(1 for e in all_industry_etfs if e["stage"] == 2)
                    
                    etf_rotation = {
                        "as_of_date": str(etf_latest_date),
                        "sector_etfs": sector_etfs_data,
                        "top_10_industry_etfs": all_industry_etfs[:10],
                        "bottom_10_industry_etfs": all_industry_etfs[-10:] if len(all_industry_etfs) >= 10 else all_industry_etfs,
                        "total_industry_etfs": total_ind,
                        "etfs_above_50dma_pct": round(above_50_count / total_ind * 100, 1) if total_ind > 0 else 0,
                        "etfs_above_200dma_pct": round(above_200_count / total_ind * 100, 1) if total_ind > 0 else 0,
                        "etfs_in_stage2_pct": round(stage2_count_etf / total_ind * 100, 1) if total_ind > 0 else 0,
                    }
            except Exception as etf_err:
                import traceback
                print(f"ETF rotation data error: {etf_err}\n{traceback.format_exc()}")
                etf_rotation = None

        return {
            "market": market,
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
            "etf_rotation": etf_rotation,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
