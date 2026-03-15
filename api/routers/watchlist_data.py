"""
Watchlist Data Router — proxies TradingView global scanner to bypass CORS.
Returns grouped live performance/indicator data for the default watchlist.
"""
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List
import httpx

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])

# ---------------------------------------------------------------------------
# Watchlist definition — groups and tickers in TradingView format
# ---------------------------------------------------------------------------
WATCHLIST_GROUPS = [
    {"name": "INDEXES",         "tickers": ["AMEX:SPY","NASDAQ:QQQ","AMEX:IWM","CBOE:ARKK","TVC:US10Y","NASDAQ:QQQE","AMEX:RSP","CBOE:MAGS","AMEX:FFTY","INDEX:MMTW","TVC:DXY","TVC:VIX","NYMEX:CL1!","COMEX:GC1!","TVC:SILVER","COINBASE:BTCUSD","CME_MINI:ES1!","CME_MINI:NQ1!","CME_MINI:RTY1!"]},
    {"name": "LONGS",           "tickers": ["NASDAQ:SNDK"]},
    {"name": "FOCUS",           "tickers": ["NASDAQ:NBIS","NYSE:CIEN","NASDAQ:VIAV","NYSE:NEE","NYSE:YOU","NASDAQ:LITE","NASDAQ:SOLS"]},
    {"name": "SOFTWARE",        "tickers": ["NASDAQ:FSLY","NYSE:CRCL","NYSE:DOCN","NYSE:NET","NYSE:DELL","NYSE:TWLO","NYSE:RNG"]},
    {"name": "SEMICONDUCTORS",  "tickers": ["NASDAQ:NVDA","NYSE:VRT","NYSE:Q","NASDAQ:INTC","NASDAQ:LRCX","NASDAQ:ASML","NASDAQ:TER","NASDAQ:AMD","NASDAQ:AVGO"]},
    {"name": "DATA / MEMORY",   "tickers": ["NASDAQ:MU","NASDAQ:WDC","NASDAQ:STX"]},
    {"name": "OPTICS",          "tickers": ["NASDAQ:AAOI","NYSE:GLW","NYSE:COHR","NASDAQ:VICR"]},
    {"name": "SPACE",           "tickers": ["NYSE:PL","NASDAQ:ASTS","NASDAQ:RKLB","NASDAQ:LUNR","NASDAQ:KTOS","NYSE:KRMN"]},
    {"name": "RETAIL",          "tickers": ["NYSE:BURL","NASDAQ:FIVE","NASDAQ:ASO"]},
    {"name": "MAG 7",           "tickers": ["NASDAQ:GOOGL","NASDAQ:MSFT","NASDAQ:AAPL","NASDAQ:META","NASDAQ:NFLX","NASDAQ:AMZN","NASDAQ:TSLA"]},
    {"name": "DATA CENTERS",    "tickers": ["NASDAQ:APLD","NASDAQ:HUT","NASDAQ:WULF","NASDAQ:RIOT","NASDAQ:IREN","NASDAQ:CRWV"]},
    {"name": "AI POWER / NUCLEAR", "tickers": ["NYSE:BE","NYSE:GEV","AMEX:URA","NYSE:CCJ","AMEX:UUUU","NYSE:BTU","AMEX:UEC","NYSE:ATI"]},
    {"name": "OIL / ENERGY",    "tickers": ["NASDAQ:FANG","NYSE:VLO","NYSE:XOM","NYSE:CNX","NYSE:HAL","NYSE:LBRT","NYSE:CTRA","NYSE:PR","NYSE:RIG","NYSE:CNQ"]},
    {"name": "INDUSTRIALS / MATERIALS", "tickers": ["NYSE:CAT","NYSE:GNRC","NYSE:DE","NYSE:FDX","NASDAQ:FORM","NASDAQ:ROIV","NYSE:SU","NYSE:MOD","NASDAQ:CGNX","NYSE:AA","NYSE:CAVA","NYSE:TPR","NYSE:EIX","NYSE:PWR","NASDAQ:COIN","NASDAQ:UCTT","NYSE:XPO","NASDAQ:PLTR","NYSE:AMPX","NYSE:BG","NYSE:HWM","NYSE:IRM","NYSE:STNG","NYSE:FIGS","NYSE:NE","NASDAQ:AXTI","NASDAQ:LASR"]},
]

TV_COLUMNS = [
    "Perf.W", "Perf.1M", "Perf.3M", "Perf.YTD", "Perf.Y",
    "Volatility.W", "RSI", "Mom", "Recommend.All"
]

TV_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-GB,en;q=0.5",
    "content-type": "text/plain;charset=UTF-8",
    "origin": "https://www.tradingview.com",
    "referer": "https://www.tradingview.com/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}

TV_URL = "https://scanner.tradingview.com/global/scan?label-product=popup-watchlists"


def _all_tickers() -> List[str]:
    seen = set()
    result = []
    for g in WATCHLIST_GROUPS:
        for t in g["tickers"]:
            if t not in seen:
                seen.add(t)
                result.append(t)
    return result


def _build_payload() -> Dict[str, Any]:
    return {
        "columns": TV_COLUMNS,
        "symbols": {"tickers": _all_tickers()},
    }


def _recommend_label(val) -> str:
    """Convert TradingView Recommend.All [-1,1] to string label."""
    if val is None:
        return None
    if val >= 0.5:
        return "Strong Buy"
    if val >= 0.1:
        return "Buy"
    if val > -0.1:
        return "Neutral"
    if val > -0.5:
        return "Sell"
    return "Strong Sell"


@router.get("/data")
async def get_watchlist_data() -> Dict[str, Any]:
    """
    Proxies the TradingView global scanner and returns grouped watchlist data.
    """
    payload = _build_payload()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(TV_URL, headers=TV_HEADERS, json=payload)
            r.raise_for_status()
            tv_data = r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"TradingView returned {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TradingView proxy error: {str(e)}")

    # Build a lookup: { "NASDAQ:NVDA": {col: value, ...} }
    col_count = len(TV_COLUMNS)
    ticker_data: Dict[str, Dict] = {}
    for item in tv_data.get("data", []):
        symbol = item.get("s", "")
        values = item.get("d", [])
        row: Dict[str, Any] = {"symbol": symbol}
        for i, col in enumerate(TV_COLUMNS):
            val = values[i] if i < len(values) else None
            # Normalise to float or None
            if val is not None:
                try:
                    val = round(float(val), 2)
                except (TypeError, ValueError):
                    val = None
            row[col] = val
        # Add human-readable recommend label
        row["recommend_label"] = _recommend_label(row.get("Recommend.All"))
        # Strip exchange prefix for clean display (e.g. "NASDAQ:NVDA" -> "NVDA")
        row["ticker"] = symbol.split(":")[-1] if ":" in symbol else symbol
        ticker_data[symbol] = row

    # Build grouped response
    groups = []
    for g in WATCHLIST_GROUPS:
        items = []
        for tv_sym in g["tickers"]:
            if tv_sym in ticker_data:
                items.append(ticker_data[tv_sym])
            else:
                # Symbol not returned by TV (e.g. futures) — include as stub
                items.append({
                    "symbol": tv_sym,
                    "ticker": tv_sym.split(":")[-1] if ":" in tv_sym else tv_sym,
                    **{col: None for col in TV_COLUMNS},
                    "recommend_label": None,
                })
        groups.append({"name": g["name"], "tickers": items})

    return {"groups": groups, "columns": TV_COLUMNS}
