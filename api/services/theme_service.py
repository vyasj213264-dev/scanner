from typing import Dict, List, Optional, Tuple
from api.database import fetch_all, fetch_val
from api.models.themes import ThemeRankRecord


def _get(row, *keys):
    """Safely extract a value from a dict trying multiple key cases."""
    for k in keys:
        if k in row:
            return row[k]
    return None


def get_themes() -> Tuple[List[ThemeRankRecord], str, Dict[str, List[str]]]:
    """
    Fetches the Sector and Industry thematic rankings from the database.
    Also returns the sector→industry mapping for drill-down navigation.
    """
    # Find the two most recent ingestion dates
    dates_sql = "SELECT DISTINCT Date FROM industry_ranks ORDER BY Date DESC LIMIT 2"
    dates_rows = fetch_all(dates_sql)
    
    if not dates_rows:
        return [], "No Data", {}
    
    latest_date = _get(dates_rows[0], 'date', 'Date')
    
    # Build sector → industry mapping from screen_data
    sector_map = get_sector_industry_map()
    
    if len(dates_rows) < 2:
        today_sql = "SELECT * FROM industry_ranks WHERE Date = ?"
        today_rows = fetch_all(today_sql, (latest_date,))
        results = [ThemeRankRecord.model_validate(row) for row in today_rows]
        return results, latest_date, sector_map

    # We have historical data to calculate Rank Movement (+/-)
    prev_date = _get(dates_rows[1], 'date', 'Date')
    
    today_sql = "SELECT * FROM industry_ranks WHERE Date = ?"
    today_rows = fetch_all(today_sql, (latest_date,))
    
    prev_sql = "SELECT * FROM industry_ranks WHERE Date = ?"
    prev_rows = fetch_all(prev_sql, (prev_date,))
    
    prev_dict = {}
    for r in prev_rows:
        cat = _get(r, 'category', 'Category')
        name = _get(r, 'name', 'Name')
        key = f"{cat}_{name}"
        prev_dict[key] = r

    results = []
    for r in today_rows:
        record = ThemeRankRecord.model_validate(r)
        
        key = f"{record.category}_{record.name}"
        if key in prev_dict:
            pr = prev_dict[key]
            
            prev_1d = _get(pr, 'rank_1d', 'Rank_1D')
            prev_1w = _get(pr, 'rank_1w', 'Rank_1W')
            prev_1m = _get(pr, 'rank_1m', 'Rank_1M')
            prev_3m = _get(pr, 'rank_3m', 'Rank_3M')
            prev_6m = _get(pr, 'rank_6m', 'Rank_6M')
            prev_1y = _get(pr, 'rank_1y', 'Rank_1Y')
            
            if prev_1d is not None: record.change_1d = prev_1d - record.rank_1d
            if prev_1w is not None: record.change_1w = prev_1w - record.rank_1w
            if prev_1m is not None: record.change_1m = prev_1m - record.rank_1m
            if prev_3m is not None: record.change_3m = prev_3m - record.rank_3m
            if prev_6m is not None: record.change_6m = prev_6m - record.rank_6m
            if prev_1y is not None: record.change_1y = prev_1y - record.rank_1y
            
        results.append(record)
        
    return results, latest_date, sector_map


def get_sector_industry_map() -> Dict[str, List[str]]:
    """
    Returns a mapping of Sector -> list of Industry names from screen_data.
    Used for the drill-down navigation.
    """
    sql = "SELECT DISTINCT Sector, Industry FROM screen_data WHERE Sector != 'Unknown' AND Industry != 'Unknown' ORDER BY Sector, Industry"
    rows = fetch_all(sql)
    
    mapping: Dict[str, List[str]] = {}
    for r in rows:
        sector = _get(r, 'sector', 'Sector') or 'Unknown'
        industry = _get(r, 'industry', 'Industry') or 'Unknown'
        if sector != 'Unknown' and industry != 'Unknown':
            if sector not in mapping:
                mapping[sector] = []
            if industry not in mapping[sector]:
                mapping[sector].append(industry)
    
    return mapping


def get_themes_stocks(
    category: str,
    name: str,
    min_market_cap: Optional[float] = None,
    min_adr: Optional[float] = None,
    max_adr: Optional[float] = None,
    min_price: Optional[float] = None,
) -> Tuple[list, int, str]:
    """
    Fetches all stocks in a given Sector or Industry from screen_data with optional sub-filters.
    Returns (rows, total_universe_count, last_updated).
    """
    col = "Sector" if category.lower() == "sector" else "Industry"
    
    extra_where = ""
    params = [name]
    
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

    sql = f"SELECT * FROM screen_data WHERE {col} = ?{extra_where} ORDER BY RS_Rating DESC NULLS LAST"
    rows = fetch_all(sql, tuple(params))
    
    universe_count = fetch_val("SELECT COUNT(*) FROM screen_data") or 0
    last_updated_row = fetch_all("SELECT MAX(Date) as last_date FROM screen_data")
    last_updated = _get(last_updated_row[0], 'last_date', 'max') if last_updated_row else None
    
    return rows, universe_count, last_updated


def get_theme_proxies(category: str, name: str, limit: int = 10) -> List[str]:
    """
    Fetches up to `limit` highly liquid/weighted tickers for a given Sector or Industry.
    This is used to build arithmetic string charts (e.g. (AAPL+MSFT)/2) when no 
    direct ETF exists.
    """
    col = "Sector" if category.lower() == "sector" else "Industry"
    
    # We ideally want the highest volume/market cap stocks. 
    # screen_data has RVOL and Close, but we'll try to sort by (Close * Volume) if volume exists, 
    # otherwise we'll just sort by RS_Rating + price to get leaders.
    sql = f"""
    SELECT Ticker 
    FROM screen_data 
    WHERE {col} = ? 
    ORDER BY (Close * RVOL) DESC NULLS LAST 
    LIMIT ?
    """
    rows = fetch_all(sql, (name, limit))
    
    # If the database structure makes (Close * RVOL) fail or yield nulls, fallback to RS_Rating
    if not rows:
        sql_fallback = f"""
        SELECT Ticker 
        FROM screen_data 
        WHERE {col} = ? 
        ORDER BY RS_Rating DESC NULLS LAST 
        LIMIT ?
        """
        rows = fetch_all(sql_fallback, (name, limit))

    return [_get(r, 'ticker', 'Ticker') for r in rows if _get(r, 'ticker', 'Ticker')]
