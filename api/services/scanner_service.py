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
        id="horizontal-resistance",
        label="Horizontal Resistance",
        description="Stocks testing a key horizontal resistance level with above-average volume.",
        category="Trend & Breakout",
    ),
    ScannerMeta(
        id="tight-setup",
        label="Tight Setups",
        description="Stage 2 stocks with low volatility consolidation (price range < 2% over 4 days).",
        category="Trend & Breakout",
    ),
    ScannerMeta(
        id="rs-high-before-price-high",
        label="RS High Before Price High",
        description="RS Rating > 90 while price is still > 5% below its 52-week high — leadership building.",
        category="Trend & Breakout",
    ),
    ScannerMeta(
        id="momentum",
        label="Momentum (1M > 10%)",
        description="Stage 2 stocks with > 10% price gain over the last month.",
        category="Trend & Breakout",
    ),
    # Pattern Recognition
    ScannerMeta(
        id="vcp",
        label="VCP Approximation",
        description="Volatility Contraction Pattern: today's range < 30% of 10-day avg range, low volume.",
        category="Pattern Recognition",
    ),
    ScannerMeta(
        id="inside-bar",
        label="Inside Bar",
        description="Today's high/low completely inside yesterday's — a volatility squeeze signal.",
        category="Pattern Recognition",
    ),
    # Volume & Events
    ScannerMeta(
        id="gap-up",
        label="Gap Up (> 2%)",
        description="Stocks that gapped up more than 2% on the open with elevated volume.",
        category="Volume & Events",
    ),
    ScannerMeta(
        id="gap-down",
        label="Gap Down (< -2%)",
        description="Stocks that gapped down more than 2% on the open with elevated volume.",
        category="Volume & Events",
    ),
    ScannerMeta(
        id="golden-crossover",
        label="Golden Crossover",
        description="50 SMA crossed above the 200 SMA today — fresh bullish trend signal.",
        category="Volume & Events",
    ),
    ScannerMeta(
        id="high-volume",
        label="High Relative Volume (> 3x)",
        description="Stocks trading at more than 3× their 50-day average volume.",
        category="Volume & Events",
    ),
    # Market Breadth
    ScannerMeta(
        id="stage-2",
        label="All Stage 2 Stocks",
        description="Full universe filtered to stocks in a Stage 2 uptrend (Minervini criteria).",
        category="Market Breadth",
    ),
    # Pullbacks
    ScannerMeta(
        id="pullback-5dma",
        label="Pullback to 5DMA",
        description="Price within +/- 2% of the 5-day moving average.",
        category="Pullbacks",
    ),
    ScannerMeta(
        id="pullback-9dma",
        label="Pullback to 9DMA",
        description="Price within +/- 2% of the 9-day moving average.",
        category="Pullbacks",
    ),
    ScannerMeta(
        id="pullback-21dma",
        label="Pullback to 21DMA",
        description="Price within +/- 2% of the 21-day moving average.",
        category="Pullbacks",
    ),
    ScannerMeta(
        id="pullback-50dma",
        label="Pullback to 50DMA",
        description="Price within +/- 2% of the 50-day moving average.",
        category="Pullbacks",
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
}

# ---------------------------------------------------------------------------
# Baseline filter — applied to EVERY scanner query as a global pre-processor.
# Stocks that fail these checks are kept in the DB but never surfaced in results.
# ---------------------------------------------------------------------------
BASELINE_FILTER = "Close >= 5"  # exclude penny stocks (price < $5)

SortField = Literal["rs_rating", "rvol", "close", "pct_from_52w_high", "momentum_1m"]
SortOrder = Literal["asc", "desc"]

_SORT_COLUMN_MAP: dict = {
    "rs_rating":        "RS_Rating",
    "rvol":             "RVOL",
    "close":            "Close",
    "pct_from_52w_high": "Pct_From_52W_High",
    "momentum_1m":      "Momentum_1M",
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
) -> Tuple[List[StockResult], int, Optional[str]]:
    """
    Execute a scanner query with optional sub-filters.

    Sub-filters (Market Cap, ADR%, Price) are applied as additional WHERE clauses.
    The pre-computed scanner_results cache is still used for the base scanner match.

    Returns:
        (results, total_universe_in_db, last_updated_date)
    """
    if scanner_id not in _FILTERS:
        raise ValueError(f"Unknown scanner ID: '{scanner_id}'")

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

    sql = (
        f"SELECT d.* FROM screen_data d "
        f"INNER JOIN scanner_results r ON d.Ticker = r.Ticker "
        f"WHERE r.scanner_id = ? AND d.{BASELINE_FILTER}{extra_where} "
        f"ORDER BY d.{sort_col} {sort_dir} "
        f"LIMIT ?"
    )
    params.append(limit)

    rows = fetch_all(sql, tuple(params))
    results = [StockResult.model_validate(row) for row in rows]

    universe = fetch_val(f"SELECT COUNT(*) FROM screen_data WHERE {BASELINE_FILTER}") or 0
    last_updated = get_last_updated()

    return results, universe, last_updated

def get_universe(
    min_market_cap: Optional[float] = None,
    min_adr: Optional[float] = None,
    max_adr: Optional[float] = None,
    min_price: Optional[float] = None,
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

    sql = (
        f"SELECT Ticker, Close, Sector, Industry, Market_Cap, ADR_20, "
        f"Momentum_1D, Momentum_1W, Momentum_1M, "
        f"Momentum_3M, Momentum_6M, Momentum_1Y "
        f"FROM screen_data WHERE {BASELINE_FILTER}{extra_where}"
    )
    rows = fetch_all(sql, tuple(params))
    last_updated = get_last_updated()
    
    # We implicitly know the universe since we just fetched it identically
    return rows, len(rows), last_updated
