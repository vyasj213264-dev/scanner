from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
import traceback
from api.database import fetch_all

router = APIRouter(prefix="/api/v1/trade-portal", tags=["Trade Portal"])

def get_market_bias(market: str = "US") -> Dict[str, Any]:
    if market == "US":
        s_tic, q_tic, i_tic = 'SPY', 'QQQ', 'IWM'
        s_txt, q_txt, i_txt = 'SPY', 'QQQ', 'Small-caps (IWM)'
    else:
        s_tic, q_tic, i_tic = '^NSEI', 'BANKNIFTY.NS', '^CRSMA'
        s_txt, q_txt, i_txt = 'Nifty 50', 'Bank Nifty', 'Mid-caps (Nifty Midcap 100)'

    # 1. Overall Market Bias
    rows = fetch_all(f"""
        SELECT Ticker, Close, SMA_20, SMA_50, SMA_200 
        FROM screen_data 
        WHERE Market = ? AND Ticker IN (?, ?, ?)
    """, (market, s_tic, q_tic, i_tic))
    
    if not rows:
        return {"bias": "Neutral", "exposure_pct": 50, "text": f"Neutral. Insufficient data to determine {market} market bias."}
    
    data = {r['Ticker']: dict(r) for r in rows}
    spy = data.get(s_tic)
    qqq = data.get(q_tic)
    iwm = data.get(i_tic)
    
    if not spy or not qqq:
        return {"bias": "Neutral", "exposure_pct": 50, "text": f"Neutral. Missing {s_txt} or {q_txt} data."}
        
    spy_above_50 = spy['Close'] > spy['SMA_50'] if spy['SMA_50'] else False
    spy_above_20 = spy['Close'] > spy['SMA_20'] if spy['SMA_20'] else False
    qqq_above_50 = qqq['Close'] > qqq['SMA_50'] if qqq['SMA_50'] else False
    
    spy_pct_50 = ((spy['Close'] - spy['SMA_50']) / spy['SMA_50'] * 100) if spy['SMA_50'] else 0
    qqq_pct_50 = ((qqq['Close'] - qqq['SMA_50']) / qqq['SMA_50'] * 100) if qqq['SMA_50'] else 0
    
    iwm_text = ""
    if iwm and iwm['SMA_50']:
        iwm_above_50 = iwm['Close'] > iwm['SMA_50']
        iwm_pct_50 = ((iwm['Close'] - iwm['SMA_50']) / iwm['SMA_50'] * 100)
        iwm_text = f" {i_txt} are {'also leading' if iwm_above_50 else 'lagging'}, trading {iwm_pct_50:+.1f}% from their 50-day."

    if spy_above_50 and qqq_above_50 and spy_above_20:
        return {
            "bias": "Risk-On", 
            "exposure_pct": 100, 
            "text": f"**Risk-On.** The broad market remains in a confirmed uptrend with both {s_txt} and {q_txt} holding firmly above their key short-term moving averages. {s_txt} is currently {spy_pct_50:+.1f}% from its 50-day moving average, signaling healthy institutional support. Tech leadership continues to drive the indices higher.{iwm_text}"
        }
    elif not spy_above_50 and not qqq_above_50:
        spy_pct_200 = ((spy['Close'] - spy['SMA_200']) / spy['SMA_200'] * 100) if spy['SMA_200'] else 0
        return {
            "bias": "Risk-Off", 
            "exposure_pct": 25, 
            "text": f"**Risk-Off.** The market has broken significant support structures, with both major indices trading below their 50-day moving averages. {s_txt} is {spy_pct_50:+.1f}% below its 50-day, indicating a shift in character toward distribution. Defensive posture is warranted until {s_txt} reclaims its moving averages.{iwm_text}"
        }
    else:
        return {
            "bias": "Neutral", 
            "exposure_pct": 50, 
            "text": f"**Neutral.** The market is exhibiting mixed signals or choppy consolidation. {s_txt} is {spy_pct_50:+.1f}% from its 50-day, while {q_txt} is {qqq_pct_50:+.1f}% from its 50-day. This divergence often precedes a larger directional move, but currently favors highly selective trading rather than aggressive exposure.{iwm_text}"
        }

def get_sector_leaderboard(market: str = "US") -> List[Dict[str, Any]]:
    # 2. Sector Leaderboard (or Custom Index Leaderboard for IN)
    found_etfs = {}
    sector_etfs = {}
    
    if market == "US":
        sector_etfs = {
            'XLK': 'Technology', 'XLY': 'Consumer Discretionary', 'XLC': 'Communication Services',
            'XLV': 'Health Care', 'XLF': 'Financials', 'XLI': 'Industrials', 
            'XLE': 'Energy', 'XLB': 'Materials', 'XLRE': 'Real Estate', 
            'XLU': 'Utilities', 'XLP': 'Consumer Staples'
        }
        
        placeholders = ','.join(['?']*len(sector_etfs))
        rows = fetch_all(f"""
            SELECT Ticker, Momentum_1W, Stage 
            FROM screen_data 
            WHERE Market = ? AND Ticker IN ({placeholders})
        """, (market, *sector_etfs.keys()))
        
        found_etfs = {r['Ticker']: {'mom': r['Momentum_1W'], 'stage': r['Stage']} for r in rows if r['Momentum_1W'] is not None}
        
        # Fallback to computing from constituents if ETF data is missing (e.g. before ingest update runs)
        if len(found_etfs) < 5:
            # Fallback query
            agg_rows = fetch_all("""
                SELECT Sector, AVG(Momentum_1W) as Avg_Mom, round(AVG(Stage)) as Avg_Stage, COUNT(*) as count
                FROM screen_data
                WHERE Market = ? AND Sector IS NOT NULL AND Sector != ''
                      AND Momentum_1W IS NOT NULL
                GROUP BY Sector
                HAVING COUNT(*) >= 5
            """, (market,))
            
            # Mappings from our DB sectors to standard names
            sector_mapping = {
                'Technology': ('XLK', 'Technology'), 'Consumer Cyclical': ('XLY', 'Consumer Discretionary'),
                'Communication Services': ('XLC', 'Communication Services'), 'Healthcare': ('XLV', 'Health Care'),
                'Financial Services': ('XLF', 'Financials'), 'Industrials': ('XLI', 'Industrials'),
                'Energy': ('XLE', 'Energy'), 'Basic Materials': ('XLB', 'Materials'),
                'Real Estate': ('XLRE', 'Real Estate'), 'Utilities': ('XLU', 'Utilities'),
                'Consumer Defensive': ('XLP', 'Consumer Staples')
            }
            
            for r in agg_rows:
                db_sector = r['Sector']
                if db_sector in sector_mapping:
                    ticker, display_name = sector_mapping[db_sector]
                    found_etfs[ticker] = {'mom': r['Avg_Mom'], 'stage': r['Avg_Stage'] or 0}
                    sector_etfs[ticker] = display_name
    else:
        # Indian Market: Use Pre-Built Custom Indices
        import json
        import os
        base_dir = os.path.dirname(os.path.dirname(__file__))
        indices_path = os.path.join(base_dir, "custom_indices_in.json")
        try:
            with open(indices_path, 'r') as f:
                indices = json.load(f)
        except Exception:
            indices = {}
            
        rows = fetch_all("SELECT Ticker, Momentum_1W, Stage FROM screen_data WHERE Market = 'IN' AND Momentum_1W IS NOT NULL")
        stock_data = {r['Ticker']: {'mom': r['Momentum_1W'], 'stage': r['Stage'] or 0} for r in rows}
        
        for idx_id, data in indices.items():
            name = data.get("name", idx_id)
            symbols = data.get("constituents", [])
            valid_moms = [stock_data[s]['mom'] for s in symbols if s in stock_data]
            valid_stages = [stock_data[s]['stage'] for s in symbols if s in stock_data]
            
            if len(valid_moms) >= 3: # Require at least 3 constituents for a valid index
                avg_mom = sum(valid_moms) / len(valid_moms)
                avg_stage = sum(valid_stages) / len(valid_stages)
                found_etfs[idx_id] = {'mom': avg_mom, 'stage': round(avg_stage)}
                sector_etfs[idx_id] = name
                
    # Sort and characterize
    sorted_etfs = sorted(found_etfs.items(), key=lambda x: x[1]['mom'], reverse=True)
    leaderboard = []
    
    for rank, (ticker, data) in enumerate(sorted_etfs, 1):
        mom = data['mom']
        stage = data['stage']
        
        if rank <= 3 and mom > 0:
            char = "Leading"
        elif mom < 0 and (rank >= len(sorted_etfs) - 2 or mom < -0.02):
            char = "Lagging"
        else:
            char = "Neutral"
            
        leaderboard.append({
            "rank": rank,
            "name": sector_etfs.get(ticker, ticker),
            "ticker": ticker,
            "pct_1w": mom * 100,
            "stage": stage,
            "characterization": char
        })
        
    return leaderboard

def get_growth_opportunities(leaderboard: List[Dict], market: str = "US") -> List[Dict[str, Any]]:
    # 3. Growth Stock Opportunities
    top_3_sectors = [s['name'] for s in leaderboard[:3]]
    if not top_3_sectors:
        return []
        
    opps = []
    for sector_name in top_3_sectors:
        if market == 'US':
            # DB sector exact match mapping (heuristic)
            db_sector_match = sector_name
            if "Discretionary" in sector_name: db_sector_match = "Consumer Cyclical"
            if "Staples" in sector_name: db_sector_match = "Consumer Defensive"
            if "Materials" in sector_name: db_sector_match = "Basic Materials"
            if "Financials" in sector_name: db_sector_match = "Financial Services"
            if "Health Care" in sector_name: db_sector_match = "Healthcare"
            
            # Find top industry in this sector
            ind_rows = fetch_all("""
                SELECT Industry, COUNT(*) as count, AVG(Momentum_1W) as Avg_Mom
                FROM screen_data
                WHERE Market = ? AND Sector LIKE ? AND Momentum_1W IS NOT NULL AND Stage IN (2, 3)
                GROUP BY Industry
                HAVING COUNT(*) >= 5
                ORDER BY Avg_Mom DESC
                LIMIT 1
            """, (market, f"%{db_sector_match}%"))
            
            top_industry = ind_rows[0]['Industry'] if ind_rows else "Broad leadership"
            
            opps.append({
                "sector": sector_name,
                "interest_reason": f"Strong relative strength outperformance (+{next(s['pct_1w'] for s in leaderboard if s['name'] == sector_name):.1f}% over 1W), signaling concentrated institutional rotation into this space.",
                "watch_type": f"Focus on fundamentally sound names in the **{top_industry}** group printing tight consolidations or high tight flags near the 20 DMA.",
                "validation": "Confirmed by continued outperformance vs SPY and expanding breadth within the sector. Invalidated by a loss of the sector ETF's 20-day moving average on expanding volume."
            })
        else:
            # For IN Market, sector_name is actually the Custom Index name (like 'Defence Index')
            opps.append({
                "sector": sector_name,
                "interest_reason": f"Collective constituent momentum (+{next(s['pct_1w'] for s in leaderboard if s['name'] == sector_name):.1f}% over 1W), indicating broad appetite for this theme.",
                "watch_type": f"Focus on fundamentally sound, high RS names within the **{sector_name}** printing tight consolidations.",
                "validation": "Confirmed by continued outperformance against the Nifty 50 and expanding breadth within the index. Invalidated by a breakdown below recent collective lows."
            })
            
    return opps

def get_weekly_bias_statement(bias_dict: Dict[str, Any], market: str = "US") -> str:
    # 4. Weekly Bias Statement
    bias = bias_dict.get("bias", "Neutral")
    exp = bias_dict.get("exposure_pct", 50)
    group_term = "sectors" if market == 'US' else "custom indices"
    
    if bias == "Risk-On":
        return f"Given the clear Risk-On environment, growth stock traders should maintain an **aggressive but structured posture** with **{exp}% exposure/margin allowed**. Capital should be deployed into the strongest breakouts in the leading top-3 {group_term}. Watch the broader market's ability to hold the 20-day moving average; rapid distribution below this warrants tighter trailing stops."
    elif bias == "Risk-Off":
        return f"In this Risk-Off environment, growth stock traders must remain **highly defensive** with **maximum {exp}% gross exposure**. Cash is a solid positional anchor. Look to deploy capital tactically strictly into well-defined **Short** setups in lagging Stage 4 {group_term}. The single most important thing to watch is the formation of a tradable bottom or a reclaim of the 10-day moving average by the major averages to invalidate the downtrend."
    else:
        return f"With the market in a Neutral configuration, growth stock traders should run **balanced portfolios** targeting **around {exp}% exposure**. Rather than relying on a rising tide to lift all boats, adopt a market-neutral approach scaling into the absolute best high-RS Stage 2 longs and hedging with Stage 4 breakdown shorts."

def get_swing_trades(bias: str, market: str = "US") -> List[Dict[str, Any]]:
    # 5. Top 5 Swing Trades (Long/Short Mix based on Bias)
    trades = []
    seen_industries = set()
    
    def fetch_trades(direction: str, limit: int):
        if direction == "Long":
            min_rs = 90 if market == 'IN' else 97
            min_close = 10
            
            sql = f"""
                SELECT Ticker, Close, SMA_10, SMA_20, SMA_50, ADR_20, Stage, Sector, Industry, RS_Rating, Pct_From_52W_High, Tight_Setup, VCP_Approximation, Inside_Bar, Gap_Down
                FROM screen_data
                WHERE Market = '{market}' AND Stage IN (2, 3)
                  AND Close >= {min_close}
                  AND Volume >= 500000
                  AND RS_Rating >= {min_rs}
                  AND (Tight_Setup = TRUE OR VCP_Approximation = TRUE)
                  AND (
                      (Close >= SMA_10 AND Close <= SMA_10 * 1.05) OR 
                      (Close >= SMA_20 AND Close <= SMA_20 * 1.05) OR 
                      (Close >= SMA_50 AND Close <= SMA_50 * 1.05)
                  )
                ORDER BY RS_Rating DESC, Pct_From_52W_High ASC
                LIMIT 50
            """
        else: # Short extreme high prob ETFs / Mega caps
            large_caps = "'SPY', 'QQQ', 'IWM', 'NVDA', 'TSLA', 'AAPL', 'MSFT', 'META', 'AMZN', 'GOOGL', 'AVGO', 'AMD', 'COIN'"
            if market == 'IN':
                large_caps = "'^NSEI', 'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'ICICIBANK.NS', 'INFY.NS', 'ITC.NS', 'SBIN.NS', 'BHARTIARTL.NS', 'LT.NS'"
                
            sql = f"""
                SELECT Ticker, Close, SMA_10, SMA_20, SMA_50, ADR_20, Stage, Sector, Industry, RS_Rating, Pct_From_52W_High, Tight_Setup, VCP_Approximation, Inside_Bar, Gap_Down
                FROM screen_data
                WHERE Market = '{market}' AND Stage = 4
                  AND Volume >= 1000000
                  AND (Sector IN ('ETF', 'Index') OR Ticker IN ({large_caps}))
                  AND (Tight_Setup = TRUE OR Inside_Bar = TRUE OR Gap_Down = TRUE)
                ORDER BY RS_Rating ASC, Pct_From_52W_High ASC
                LIMIT 50
            """
            
        rows = fetch_all(sql)
        added = 0
        
        for r in rows:
            if added >= limit:
                break
                
            ind = r['Industry']
            if ind is not None and ind != "Unknown" and ind in seen_industries and added < limit - 1:
                 continue
                 
            if ind is not None and ind != "Unknown":
                seen_industries.add(ind)
            
            close = r['Close']
            adr = r['ADR_20'] if r['ADR_20'] else (close * 0.03) # Fallback 3%
            
            if direction == "Long":
                entry = close * 1.01
                stoploss = close - adr
                risk_per_share = entry - stoploss
                if risk_per_share <= 0: continue
                
                risk_pct = risk_per_share / entry
                pos_size_pct = min(0.25, 0.01 / risk_pct)
                
                setup_names = []
                if r['VCP_Approximation']: setup_names.append("Minervini Low Cheat")
                if r['Tight_Setup']: setup_names.append("Tight Consolidation")
                if r.get('Inside_Bar'): setup_names.append("Inside Bar")
                
                setup_reasons = " and ".join(setup_names) if setup_names else "Stage 2 Breakout Uptrend"
                
                trades.append({
                    "ticker": r['Ticker'],
                    "type": "LONG",
                    "industry": ind,
                    "rs_rating": r['RS_Rating'] or 0,
                    "entry": round(entry, 2),
                    "stoploss": round(stoploss, 2),
                    "position_size_pct": round(pos_size_pct * 100, 1),
                    "reason": f"Stock is exhibiting an extreme high-probability {setup_reasons} near a key moving average. Strong relative strength (RS: {round(r['RS_Rating'] or 0)} >= {min_rs}) flags massive institutional accumulation.",
                    "exit_plan": f"Take 1/2 size off at {round(entry + (risk_per_share * 2), 2)} (+2R) to finance risk. Trail remaining half via a close below the 10 DMA or break of {round(stoploss, 2)}."
                })
                added += 1
            else:
                entry = close * 0.99
                stoploss = close + adr
                risk_per_share = stoploss - entry
                if risk_per_share <= 0: continue
                
                risk_pct = risk_per_share / entry
                pos_size_pct = min(0.25, 0.01 / risk_pct)
                
                setup_names = []
                if r.get('Tight_Setup'): setup_names.append("Tight Consolidation (Bear Flag)")
                if r.get('Inside_Bar'): setup_names.append("Inside Bar")
                if r.get('Gap_Down'): setup_names.append("Gap Down Continuation")
                
                setup_reasons = " and ".join(setup_names) if setup_names else "Stage 4 Downtrend"
                
                trades.append({
                    "ticker": r['Ticker'],
                    "type": "SHORT",
                    "industry": ind,
                    "rs_rating": r['RS_Rating'] or 0,
                    "entry": round(entry, 2),
                    "stoploss": round(stoploss, 2),
                    "position_size_pct": round(pos_size_pct * 100, 1),
                    "reason": f"High liquidity underlying asset is printing a {setup_reasons} breakdown pattern embedded in a structural Stage 4 macro downtrend. Valid for Leveraged Inverse ETF proxies or direct shorting.",
                    "exit_plan": f"Cover 1/2 size at {round(entry - (risk_per_share * 2), 2)} (+2R). Trail remaining half via a close above the 10 DMA or break of {round(stoploss, 2)}."
                })
                added += 1

    # Indian market: only Long trades when environment favors
    if market == 'IN':
        if bias in ('Risk-On', 'Neutral'):
            fetch_trades("Long", 5)
        # Risk-Off: no trades for Indian market (no shorting culture)
        return trades
    
    if bias == "Risk-On":
        fetch_trades("Long", 5)
    elif bias == "Risk-Off":
        fetch_trades("Short", 5)
    else:
        fetch_trades("Long", 3)
        fetch_trades("Short", 2)
        
    return trades

@router.get("/daily-read", summary="Get the AI Daily Trade Portal Read")
def get_daily_read(market: str = Query("US", description="US or IN")):
    """Returns the synthetically generated deterministic AI market read."""
    try:
        market_up = market.upper()
        bias_dict = get_market_bias(market_up)
        trades = get_swing_trades(bias_dict.get("bias", "Neutral"), market_up)
        
        result = {
            "status": "success",
            "data": {
                "market_bias": bias_dict.get("text"),
                "exposure_pct": bias_dict.get("exposure_pct"),
                "swing_trades": trades
            }
        }
        
        # Generate Sector/Index Leaderboard and Growth Opportunities
        leaderboard = get_sector_leaderboard(market_up)
        opps = get_growth_opportunities(leaderboard, market_up)
        weekly_bias = get_weekly_bias_statement(bias_dict, market_up)
        
        result["data"]["sector_leaderboard"] = leaderboard
        result["data"]["growth_opportunities"] = opps
        result["data"]["weekly_statement"] = weekly_bias
        
        return result
    except Exception as e:
        print(f"Error in trade portal: {e}")
        raise HTTPException(status_code=500, detail=f"{e}\n{traceback.format_exc()}")
