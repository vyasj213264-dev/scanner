import json
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends
import yfinance as yf

from api.routers.auth import require_user

router = APIRouter(
    prefix="/api/v1/quotes",
    tags=["Live Quotes"],
    dependencies=[Depends(require_user)]
)

@router.get("/live", summary="Fetch live intraday quotes for a list of tickers")
def get_live_quotes(tickers: str = Query(..., description="Comma-separated list of tickers")):
    """
    Returns the live current price and the percentage change from yesterday's close.
    Uses yfinance to batch download a 5-day history and extract the latest intraday price.
    """
    if not tickers:
        return {"status": "success", "data": {}}
        
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return {"status": "success", "data": {}}
        
    try:
        # Download recent data. period="5d" ensures we have the previous close even over a long weekend
        data = yf.download(ticker_list, period="5d", interval="1d", progress=False, group_by="ticker")
        
        results = {}
        
        if len(ticker_list) == 1:
            # yfinance returns a flat dataframe if only 1 ticker
            ticker = ticker_list[0]
            if not data.empty and len(data) >= 2:
                # The last row is the current live price (or last close if market closed)
                current_price = float(data['Close'].iloc[-1])
                # The second to last row is the previous close
                prev_close = float(data['Close'].iloc[-2])
                
                pct_change = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0
                results[ticker] = {
                    "price": current_price,
                    "change_pct": pct_change
                }
        else:
            # yfinance returns a multi-index dataframe when multiple tickers
            for ticker in ticker_list:
                try:
                    if ticker in data and not data[ticker].empty and len(data[ticker]) >= 2:
                        current_price = float(data[ticker]['Close'].iloc[-1])
                        prev_close = float(data[ticker]['Close'].iloc[-2])
                        pct_change = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0
                        
                        results[ticker] = {
                            "price": current_price,
                            "change_pct": pct_change
                        }
                except Exception as e:
                    # Ignore missing/delisted tickers
                    pass
                    
        return {"status": "success", "data": results}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
