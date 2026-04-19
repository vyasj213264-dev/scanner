"""
Scanner service — all business logic for stock scans.
Translates scanner type strings into parameterised SQL queries
and returns typed StockResult lists.
"""
from typing import List, Literal, Optional, Tuple

from api.database import fetch_all, fetch_val, get_universe_count_in_db, get_last_updated
from api.models.scanner import StockResult, ScannerMeta

# ---------------------------------------------------------------------------
# Scanner catalogue — single source of truth for IDs, labels, descriptions
# ---------------------------------------------------------------------------

SCANNER_CATALOGUE: List[ScannerMeta] = [
    # Trend & Breakout
    ScannerMeta(
        id="minervini-cheat",
        label="🎯 Minervini Cheat Entry",
        description="Stage 2 leaders with volume dry-up and price hugging the 10/20 DMA inside a VCP — early entry before the pivot breakout.",
        category="Elite Scanners",
        criteria=[
            "Trend: Classic Stage 2 Uptrend (Price > 150DMA > 200DMA, 200DMA trending up)",
            "Momentum: Overall RS Rating >= 70, 3-Month Momentum > +10%",
            "Price Structure: Trading within 25% of the 52-week high",
            "Consolidation: Price is hugging within 3% of either the 10-day or 20-day Simple Moving Average",
            "Pattern: VCP Approximation (Today's High-Low range < 30% of the 10-day average daily range)",
            "Volume: Dry-up (Today's volume is < 85% of the 50-day average)"
        ]
    ),
    ScannerMeta(
        id="htf",
        label="🚀 High Tight Flag",
        description="Stocks that surged 90%+ in 3 months and are now forming a tight flag consolidation (2–25% off highs) with volume dry-up. Rare, high-conviction setup.",
        category="Elite Scanners",
        criteria=[
            "Trend: Classic Stage 2 Uptrend",
            "Momentum: Extreme 3-Month Momentum > +90%, RS Rating >= 80",
            "Price Structure: Pulling back between -2% and -25% from the 52-week high",
            "Volatility: Average Daily Range (20-day) >= 4.0%",
            "Volume: Dry-up (Today's volume is < 85% of the 50-day average)"
        ]
    ),
    ScannerMeta(
        id="horizontal-resistance",
        label="Horizontal Resistance",
        description="Stocks testing a key horizontal resistance level with above-average volume.",
        category="Core Patterns & Setups",
        criteria=[
            "Price Structure: Current close is within ±2% of the highest high over the last 126 trading days (~6 months)",
            "Volume: Above-average daily volume (RVOL > 1.0)"
        ]
    ),
    ScannerMeta(
        id="tight-setup",
        label="Tight Setups",
        description="Stage 2 stocks with low volatility consolidation (price range < 2% over 4 days).",
        category="Core Patterns & Setups",
        criteria=[
            "Trend: Classic Stage 2 Uptrend",
            "Pattern: Tight Setup (Maximum price difference between the highs and lows of the last 4 closing prices is < 2%)",
            "Volume: Below-average daily volume (RVOL < 1.0)"
        ]
    ),
    ScannerMeta(
        id="rs-high-before-price-high",
        label="RS High Before Price High",
        description="RS Rating > 90 while price is still > 5% below its 52-week high — leadership building.",
        category="Momentum & Trend",
        criteria=[
            "Momentum: Overall RS Rating > 90",
            "Price Structure: Price is taking a breather, currently > 5% below its 52-week high"
        ]
    ),
    ScannerMeta(
        id="momentum",
        label="Momentum (1M > 10%)",
        description="Stage 2 stocks with > 10% price gain over the last month.",
        category="Momentum & Trend",
        criteria=[
            "Trend: Classic Stage 2 Uptrend",
            "Momentum: Price has gained more than 10% over the last 21 trading days (~1 month)"
        ]
    ),
    # Pattern Recognition
    ScannerMeta(
        id="vcp",
        label="VCP Approximation",
        description="Volatility Contraction Pattern: today's range < 30% of 10-day avg range, low volume.",
        category="Core Patterns & Setups",
        criteria=[
            "Trend: Classic Stage 2 Uptrend",
            "Pattern: Volatility Contraction (Today's High-Low range < 30% of the 10-day average daily range)",
            "Volume: Below 50-day average volume"
        ]
    ),
    ScannerMeta(
        id="inside-bar",
        label="Inside Bar",
        description="Today's high/low completely inside yesterday's — a volatility squeeze signal.",
        category="Core Patterns & Setups",
        criteria=[
            "Pattern: Inside Bar (Today's high is lower than yesterday's high AND today's low is higher than yesterday's low)",
            "Volume: Below-average daily volume (RVOL < 1.0)"
        ]
    ),
    # Volume & Events
    # ScannerMeta(
    #     id="gap-up",
    #     label="Gap Up (> 2%)",
    #     description="Stocks that gapped up more than 2% on the open with elevated volume.",
    #     category="Volume & Events",
    #     criteria=[
    #         "Price Action: Opened more than 2% above yesterday's closing price",
    #         "Volume: Strong volume accumulation (RVOL > 1.5x average)"
    #     ]
    # ), 
    # ScannerMeta(
    #     id="gap-down",
    #     label="Gap Down (< -2%)",
    #     description="Stocks that gapped down more than 2% on the open with elevated volume.",
    #     category="Volume & Events",
    #     criteria=[
    #         "Price Action: Opened more than 2% below yesterday's closing price",
    #         "Volume: Strong volume distribution (RVOL > 1.5x average)"
    #     ]
    # ),
    ScannerMeta(
        id="golden-crossover",
        label="Golden Crossover",
        description="50 SMA crossed above the 200 SMA today — fresh bullish trend signal.",
        category="Volume & Events",
        criteria=[
            "Trend Change: The 50-day SMA crossed completely above the 200-day SMA during today's session"
        ]
    ),
    ScannerMeta(
        id="high-volume",
        label="High Relative Volume (> 3x)",
        description="Stocks trading at more than 3× their 50-day average volume.",
        category="Volume & Events",
        criteria=[
            "Volume: Extreme volume event (More than 3 times the 50-day average daily volume)"
        ]
    ),
    # Market Breadth
    ScannerMeta(
        id="stage-2",
        label="All Stage 2 Stocks",
        description="Full universe filtered to stocks in a Stage 2 uptrend (Minervini criteria).",
        category="Momentum & Trend",
        criteria=[
            "Trend: Classic Stage 2 Uptrend (Current Price > 150DMA > 200DMA, and the 200DMA is trending upwards vs 20 days ago)"
        ]
    ),
    # Pullbacks
    ScannerMeta(
        id="pullback-5dma",
        label="Pullback to 5DMA",
        description="Price within +/- 2% of the 5-day moving average.",
        category="Mean Reversion (Pullbacks)",
        criteria=[
            "Price Structure: Current close is resting precisely within ±2% of the 5-day Simple Moving Average"
        ]
    ),
    ScannerMeta(
        id="pullback-9dma",
        label="Pullback to 9DMA",
        description="Price within +/- 2% of the 9-day moving average.",
        category="Mean Reversion (Pullbacks)",
        criteria=[
            "Price Structure: Current close is resting precisely within ±2% of the 9-day Simple Moving Average"
        ]
    ),
    ScannerMeta(
        id="pullback-21dma",
        label="Pullback to 21DMA",
        description="Price within +/- 2% of the 21-day moving average.",
        category="Mean Reversion (Pullbacks)",
        criteria=[
            "Price Structure: Current close is resting precisely within ±2% of the 21-day Simple Moving Average"
        ]
    ),
    ScannerMeta(
        id="pullback-50dma",
        label="Pullback to 50DMA",
        description="Price within +/- 2% of the 50-day moving average.",
        category="Mean Reversion (Pullbacks)",
        criteria=[
            "Price Structure: Current close is resting precisely within ±2% of the 50-day Simple Moving Average"
        ]
    ),
    # Modern Swing Scanners
    ScannerMeta(
        id="modern-breakout",
        label="⚡ Modern Breakout Leaders",
        description="Liquid Stage 2 leaders (RS >= 95) near 52-week highs with constructive tight/VCP/inside-bar patterns — prime breakout candidates for 2–10 day swings.",
        category="Elite Scanners",
        criteria=[
            "Trend: Classic Stage 2 Uptrend",
            "Momentum: Extreme RS Rating >= 95",
            "Price Structure: Trading within 20% of the 52-week high, and Price is within 6% of the 20-day SMA",
            "Consolidation Pattern: Must be forming either a Tight Setup (4-day close range < 2%), an Inside Bar, or a VCP Approximation"
        ]
    ),
    ScannerMeta(
        id="modern-pullback",
        label="🔄 Modern Pullback Continuation",
        description="Stage 2 leaders (RS >= 90) pulling back to the 10/20 DMA with volume contraction and tight patterns — continuation entry setups.",
        category="Elite Scanners",
        criteria=[
            "Trend: Classic Stage 2 Uptrend (Price > 50DMA, 20DMA > 50DMA)",
            "Momentum: Strong RS Rating >= 90",
            "The Pullback: Price is tightly hugging within ±2% of either the 10-day or 20-day SMA",
            "Volume: Dry-up (RVOL < 1.0)",
            "Consolidation Pattern: Must be forming either a Tight Setup (4-day close range < 2%), an Inside Bar, or a VCP Approximation"
        ]
    ),
    # Elite Scanners
    ScannerMeta(
        id="power-pullback",
        label="🔥 Power Pullback",
        description="Institutional-grade pullback scanner: liquid stocks ($20M+ avg daily $ vol) in a gentle 3SMA pullback (-0.5% to -3%), above key MAs, in a top-50% performing industry, showing a reversal/pause signal (upside reversal, tight setup, inside day, double inside day, or VCP).",
        category="Elite Scanners",
        criteria=[
            "Liquidity: Institutional grade volume (20-day Average Dollar Volume > $20,000,000)",
            "Momentum: 6-Month RS Rating >= 80",
            "Trend Maintenance: Price > 50DMA and Price is within 5% of the 21DMA",
            "The Pullback: The 3-day Moving Average exhibits a gentle downward slope between -0.5% and -3% vs 3 days ago",
            "Reversal Signal: Must trigger either an Upside Reversal (Hammer, Pin Bar, or Volume Reversal), a Double Inside Day, an Inside Bar, a Tight Setup, or VCP"
        ]
    ),
    ScannerMeta(
        id="leading-industry-stock",
        label="🏆 Leading Industry + Leading Stock",
        description="O'Neil's golden rule: buy the best stocks in the best industries. Finds Stage 2 leaders (RS >= 85) whose IBD industry ETF proxy is ranked in the top 20 by 3M momentum AND trading above its 50DMA. Only shows stocks with $10+ price and mapped IBD ETF proxy.",
        category="Elite Scanners",
        criteria=[
            "Industry Leadership: The stock's mapped IBD Industry ETF proxy is ranked in the Top 20 across the entire market for 3-Month Momentum AND the ETF itself is trading > 50DMA",
            "Stock Leadership: Stan Weinstein Stage 2 Uptrend AND Overall RS Rating >= 85",
            "Baselines: Must have a valid IBD ETF proxy mapping, and Price >= $10"
        ]
    ),
]

# Lookup by id for O(1) access
_CATALOGUE_BY_ID = {s.id: s for s in SCANNER_CATALOGUE}


def get_scanner_meta(scanner_id: str) -> Optional[ScannerMeta]:
    return _CATALOGUE_BY_ID.get(scanner_id)


# ---------------------------------------------------------------------------
# SQL filter definitions
# ---------------------------------------------------------------------------

_FILTERS: dict = {
    "minervini-cheat":        (
        "In_Stage_2 AND RS_Rating >= 70 AND RVOL < 0.85 AND VCP_Approximation "
        "AND Momentum_3M > 0.10 AND Pct_From_52W_High > -25 "
        "AND (abs(Close - SMA_10) / SMA_10 <= 0.03 OR abs(Close - SMA_20) / SMA_20 <= 0.03)"
    ),
    "htf": (
        "In_Stage_2 AND Momentum_3M > 0.90 "
        "AND Pct_From_52W_High BETWEEN -25 AND -2 "
        "AND RVOL < 0.85 AND RS_Rating >= 80 AND ADR_20 >= 4.0"
    ),
    "horizontal-resistance": "Near_Horizontal_Resistance AND RVOL > 1.0",
    "tight-setup":            "Tight_Setup AND In_Stage_2 AND RVOL < 1.0",
    "rs-high-before-price-high": "RS_Rating > 90 AND Pct_From_52W_High < -5",
    "momentum":               "Momentum_1M > 0.1 AND In_Stage_2",
    "vcp":                    "VCP_Approximation AND In_Stage_2",
    "inside-bar":             "Inside_Bar AND RVOL < 1.0",
    "gap-up":                 "Gap_Up AND RVOL > 1.5",
    "gap-down":               "Gap_Down AND RVOL > 1.5",
    "golden-crossover":       "Golden_Crossover",
    "high-volume":            "RVOL > 3.0",
    "stage-2":                "In_Stage_2",
    "pullback-5dma":          "abs(Close - SMA_5) / SMA_5 <= 0.02",
    "pullback-9dma":          "abs(Close - SMA_9) / SMA_9 <= 0.02",
    "pullback-21dma":         "abs(Close - SMA_21) / SMA_21 <= 0.02",
    "pullback-50dma":         "abs(Close - SMA_50) / SMA_50 <= 0.02",
    "long-term-pf":           "f.peg_ratio > 0 AND f.peg_ratio < 1.5 AND f.revenue_doubled IS TRUE AND d.In_Stage_2 IS TRUE AND d.Market_Cap >= 500",
    "modern-breakout":        (
        "In_Stage_2 AND RS_Rating >= 95 AND Pct_From_52W_High > -20 "
        "AND (Tight_Setup OR VCP_Approximation OR Inside_Bar) "
        "AND abs(Close - SMA_20) / SMA_20 <= 0.06"
    ),
    "modern-pullback":        (
        "In_Stage_2 AND RS_Rating >= 90 AND Close >= SMA_50 AND SMA_20 >= SMA_50 "
        "AND RVOL < 1.0 "
        "AND ((abs(Close - SMA_20) / SMA_20 <= 0.02) OR (abs(Close - SMA_10) / SMA_10 <= 0.02)) "
        "AND (Inside_Bar OR Tight_Setup OR VCP_Approximation)"
    ),
    "power-pullback":         (
        "Avg_Dollar_Vol_20 > 20000000 "
        "AND SMA_3_Slope BETWEEN -0.03 AND -0.005 "
        "AND Close > SMA_50 "
        "AND Close >= SMA_21 * 0.95 "
        "AND RS_Rating_6M >= 80 "
        "AND (Upside_Reversal OR Tight_Setup OR Inside_Bar OR Double_Inside_Day OR VCP_Approximation)"
    ),
    "leading-industry-stock": (
        "d.Stage = 2 "
        "AND d.RS_Rating >= 85 "
        "AND d.Close >= 10 "
        "AND d.IBD_ETF_Proxy IS NOT NULL "
        "AND etf.Rank_3M <= 20 "
        "AND etf.Above_50DMA IS TRUE"
    ),
}

# ---------------------------------------------------------------------------
# Baseline filter — applied to EVERY scanner query as a global pre-processor.
# Stocks that fail these checks are kept in the DB but never surfaced in results.
# ---------------------------------------------------------------------------
def get_baseline_filter(market: str = "US") -> str:
    """Returns the baseline price filter for the given market."""
    if market == "IN":
        return "Close > 0"  # INR-denominated, no $5 filter
    return "Close >= 5"  # USD penny stock filter

BASELINE_FILTER = "Close >= 5"  # default for backward compat

SortField = Literal["rs_rating", "rvol", "close", "pct_from_52w_high", "momentum_1m", "ticker", "peg_ratio", "revenue_growth_3y"]
SortOrder = Literal["asc", "desc"]

_SORT_COLUMN_MAP: dict = {
    "rs_rating":        "RS_Rating",
    "rvol":             "RVOL",
    "close":            "Close",
    "pct_from_52w_high": "Pct_From_52W_High",
    "momentum_1m":      "Momentum_1M",
    "ticker":           "Ticker",
    "peg_ratio":        "f.peg_ratio",
    "revenue_growth_3y": "f.revenue_growth_3y",
}


def run_scan(
    scanner_id: str,
    limit: int = 20,
    sort_by: SortField = "rs_rating",
    order: SortOrder = "desc",
    min_market_cap: Optional[float] = None,
    min_adr: Optional[float] = None,
    max_adr: Optional[float] = None,
    min_price: Optional[float] = None,
    include_sectors: Optional[List[str]] = None,
    exclude_sectors: Optional[List[str]] = None,
    include_industries: Optional[List[str]] = None,
    exclude_industries: Optional[List[str]] = None,
    market: str = "US",
) -> Tuple[List[StockResult], int, Optional[str]]:
    """
    Execute a scanner query with optional sub-filters.

    Sub-filters (Market Cap, ADR%, Price, Sector, Industry) are applied as additional WHERE clauses.
    The pre-computed scanner_results cache is still used for the base scanner match.

    Returns:
        (results, total_universe_in_db, last_updated_date)
    """
    if scanner_id not in _FILTERS:
        raise ValueError(f"Unknown scanner ID: '{scanner_id}'")

    baseline = get_baseline_filter(market)
    sort_col = _SORT_COLUMN_MAP.get(sort_by, "RS_Rating")
    sort_dir = "DESC" if order == "desc" else "ASC"

    # Build dynamic sub-filter clauses
    extra_where = ""
    params = [scanner_id]
    
    if min_market_cap is not None:
        extra_where += " AND d.Market_Cap >= ?"
        params.append(min_market_cap)
    if min_adr is not None:
        extra_where += " AND d.ADR_20 >= ?"
        params.append(min_adr)
    if max_adr is not None:
        extra_where += " AND d.ADR_20 <= ?"
        params.append(max_adr)
    if min_price is not None:
        extra_where += " AND d.Close >= ?"
        params.append(min_price)

    # Sector/Industry filtering
    if include_sectors:
        placeholders = ",".join(["?" for _ in include_sectors])
        extra_where += f" AND d.Sector IN ({placeholders})"
        params.extend(include_sectors)
    if exclude_sectors:
        placeholders = ",".join(["?" for _ in exclude_sectors])
        extra_where += f" AND d.Sector NOT IN ({placeholders})"
        params.extend(exclude_sectors)
        
    if include_industries:
        placeholders = ",".join(["?" for _ in include_industries])
        extra_where += f" AND d.Industry IN ({placeholders})"
        params.extend(include_industries)
    if exclude_industries:
        placeholders = ",".join(["?" for _ in exclude_industries])
        extra_where += f" AND d.Industry NOT IN ({placeholders})"
        params.extend(exclude_industries)

    # Join industry_ranks twice: once for Sector, once for Industry
    # We use MAX(Date) or just the most recent available date by joining without Date filter,
    # relying on the DB clean-up keeping only the last 5 days and joining by Category and Name.
    # To be precise, we join on the latest date holding ranks.
    latest_date_query = f"(SELECT MAX(Date) FROM industry_ranks WHERE Market = '{market}')"
    
    sql = (
        f"SELECT d.*, "
        f"f.peg_ratio AS peg_ratio, f.revenue_growth_3y AS revenue_growth_3y, "
        f"sr.Rank_1D AS Sector_Rank_1D, sr.Rank_1W AS Sector_Rank_1W, "
        f"sr.Rank_1M AS Sector_Rank_1M, sr.Rank_3M AS Sector_Rank_3M, sr.Rank_6M AS Sector_Rank_6M, "
        f"ir.Rank_1D AS Industry_Rank_1D, ir.Rank_1W AS Industry_Rank_1W, "
        f"ir.Rank_1M AS Industry_Rank_1M, ir.Rank_3M AS Industry_Rank_3M, ir.Rank_6M AS Industry_Rank_6M "
        f"FROM screen_data d "
        f"INNER JOIN scanner_results r ON d.Ticker = r.Ticker AND r.Market = '{market}' "
        f"LEFT JOIN fundamentals_data f ON d.Ticker = f.Ticker "
        f"LEFT JOIN industry_ranks sr ON d.Sector = sr.Name AND sr.Category = 'Sector' AND sr.Market = '{market}' AND sr.Date = {latest_date_query} "
        f"LEFT JOIN industry_ranks ir ON d.Industry = ir.Name AND ir.Category = 'Industry' AND ir.Market = '{market}' AND ir.Date = {latest_date_query} "
        f"WHERE r.scanner_id = ? AND d.Market = '{market}' AND d.{baseline}{extra_where} "
        f"ORDER BY d.{sort_col} {sort_dir} "
        f"LIMIT ?"
    )
    params.append(limit)

    rows = fetch_all(sql, tuple(params))
    results = [StockResult.model_validate(row) for row in rows]

    universe = fetch_val(f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}' AND {baseline}") or 0
    last_updated = get_last_updated(market)

    return results, universe, last_updated

def get_universe(
    min_market_cap: Optional[float] = None,
    min_adr: Optional[float] = None,
    max_adr: Optional[float] = None,
    min_price: Optional[float] = None,
    include_sectors: Optional[List[str]] = None,
    exclude_sectors: Optional[List[str]] = None,
    include_industries: Optional[List[str]] = None,
    exclude_industries: Optional[List[str]] = None,
    market: str = "US",
) -> Tuple[List[dict], int, Optional[str]]:
    """
    Returns the full universe of stocks > $5 with their momentum data.
    Only fetches the specific continuous variables needed for the table
    to minimize database I/O and JSON payload size.
    """
    extra_where = ""
    params = []
    
    if min_market_cap is not None:
        extra_where += " AND Market_Cap >= ?"
        params.append(min_market_cap)
    if min_adr is not None:
        extra_where += " AND ADR_20 >= ?"
        params.append(min_adr)
    if max_adr is not None:
        extra_where += " AND ADR_20 <= ?"
        params.append(max_adr)
    if min_price is not None:
        extra_where += " AND Close >= ?"
        params.append(min_price)

    # Sector/Industry filtering
    if include_sectors:
        placeholders = ",".join(["?" for _ in include_sectors])
        extra_where += f" AND Sector IN ({placeholders})"
        params.extend(include_sectors)
    if exclude_sectors:
        placeholders = ",".join(["?" for _ in exclude_sectors])
        extra_where += f" AND Sector NOT IN ({placeholders})"
        params.extend(exclude_sectors)
        
    if include_industries:
        placeholders = ",".join(["?" for _ in include_industries])
        extra_where += f" AND Industry IN ({placeholders})"
        params.extend(include_industries)
    if exclude_industries:
        placeholders = ",".join(["?" for _ in exclude_industries])
        extra_where += f" AND Industry NOT IN ({placeholders})"
        params.extend(exclude_industries)

    latest_date_query = f"(SELECT MAX(Date) FROM industry_ranks WHERE Market = '{market}')"
    sql = (
        f"SELECT d.Ticker, d.Close, d.Sector, d.Industry, d.Market_Cap, d.ADR_20, "
        f"d.RS_Rating, d.RS_Rating_1M, d.RS_Rating_3M, d.RS_Rating_6M, d.Stage, d.RVOL, d.Pct_From_52W_High, "
        f"d.Momentum_1D, d.Momentum_1W, d.Momentum_1M, "
        f"d.Momentum_3M, d.Momentum_6M, d.Momentum_1Y, "
        f"f.peg_ratio, f.revenue_growth_3y, "
        f"sr.Rank_1D AS Sector_Rank_1D, sr.Rank_1W AS Sector_Rank_1W, "
        f"sr.Rank_1M AS Sector_Rank_1M, sr.Rank_3M AS Sector_Rank_3M, sr.Rank_6M AS Sector_Rank_6M, "
        f"ir.Rank_1D AS Industry_Rank_1D, ir.Rank_1W AS Industry_Rank_1W, "
        f"ir.Rank_1M AS Industry_Rank_1M, ir.Rank_3M AS Industry_Rank_3M, ir.Rank_6M AS Industry_Rank_6M "
        f"FROM screen_data d "
        f"LEFT JOIN fundamentals_data f ON d.Ticker = f.Ticker "
        f"LEFT JOIN industry_ranks sr ON d.Sector = sr.Name AND sr.Category = 'Sector' AND sr.Market = '{market}' AND sr.Date = {latest_date_query} "
        f"LEFT JOIN industry_ranks ir ON d.Industry = ir.Name AND ir.Category = 'Industry' AND ir.Market = '{market}' AND ir.Date = {latest_date_query} "
        f"WHERE d.Market = '{market}' AND d.{get_baseline_filter(market)}{extra_where}"
    )

    rows = fetch_all(sql, tuple(params))
    last_updated = get_last_updated(market)
    
    # We implicitly know the universe since we just fetched it identically
    return rows, len(rows), last_updated
