from typing import Dict, List, Optional, Tuple
from api.database import fetch_all, fetch_val
from api.models.themes import ThemeRankRecord


def _get(row, *keys):
    """Safely extract a value from a dict trying multiple key cases."""
    for k in keys:
        if k in row:
            return row[k]
    return None


def get_themes(market: str = "US") -> Tuple[List[ThemeRankRecord], str, Dict[str, List[str]]]:
    """
    Fetches the Sector and Industry thematic rankings from the database.
    Also returns the sector→industry mapping for drill-down navigation.
    """
    # Find the two most recent ingestion dates
    dates_sql = "SELECT DISTINCT Date FROM industry_ranks WHERE Market = ? ORDER BY Date DESC LIMIT 2"
    dates_rows = fetch_all(dates_sql, (market,))
    
    if not dates_rows:
        return [], "No Data", {}
    
    latest_date = _get(dates_rows[0], 'date', 'Date')
    
    # Build sector → industry mapping from screen_data
    sector_map = get_sector_industry_map(market)
    
    if len(dates_rows) < 2:
        today_sql = "SELECT * FROM industry_ranks WHERE Date = ? AND Market = ?"
        today_rows = fetch_all(today_sql, (latest_date, market))
        results = [ThemeRankRecord.model_validate(row) for row in today_rows]
        return results, latest_date, sector_map

    # We have historical data to calculate Rank Movement (+/-)
    prev_date = _get(dates_rows[1], 'date', 'Date')
    
    today_sql = "SELECT * FROM industry_ranks WHERE Date = ? AND Market = ?"
    today_rows = fetch_all(today_sql, (latest_date, market))
    
    prev_sql = "SELECT * FROM industry_ranks WHERE Date = ? AND Market = ?"
    prev_rows = fetch_all(prev_sql, (prev_date, market))
    
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


def get_sector_industry_map(market: str = "US") -> Dict[str, List[str]]:
    """
    Returns a mapping of Sector -> list of Industry names from screen_data.
    Used for the drill-down navigation.
    """
    sql = "SELECT DISTINCT Sector, Industry FROM screen_data WHERE Market = ? AND Sector != 'Unknown' AND Industry != 'Unknown' ORDER BY Sector, Industry"
    rows = fetch_all(sql, (market,))
    
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
    market: str = "US",
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

    latest_date_query = f"(SELECT MAX(Date) FROM industry_ranks WHERE Market = '{market}')"
    sql = (
        f"SELECT d.*, "
        f"sr.Rank_1D AS Sector_Rank_1D, sr.Rank_1W AS Sector_Rank_1W, "
        f"sr.Rank_1M AS Sector_Rank_1M, sr.Rank_3M AS Sector_Rank_3M, sr.Rank_6M AS Sector_Rank_6M, "
        f"ir.Rank_1D AS Industry_Rank_1D, ir.Rank_1W AS Industry_Rank_1W, "
        f"ir.Rank_1M AS Industry_Rank_1M, ir.Rank_3M AS Industry_Rank_3M, ir.Rank_6M AS Industry_Rank_6M "
        f"FROM screen_data d "
        f"LEFT JOIN industry_ranks sr ON d.Sector = sr.Name AND sr.Category = 'Sector' AND sr.Market = '{market}' AND sr.Date = {latest_date_query} "
        f"LEFT JOIN industry_ranks ir ON d.Industry = ir.Name AND ir.Category = 'Industry' AND ir.Market = '{market}' AND ir.Date = {latest_date_query} "
        f"WHERE d.{col} = ? AND d.Market = '{market}' {extra_where} "
        f"ORDER BY d.RS_Rating DESC NULLS LAST"
    )
    rows = fetch_all(sql, tuple(params))
    
    universe_count = fetch_val(f"SELECT COUNT(*) FROM screen_data WHERE Market = '{market}'") or 0
    last_updated_row = fetch_all(f"SELECT MAX(Date) as last_date FROM screen_data WHERE Market = '{market}'")
    last_updated = _get(last_updated_row[0], 'last_date', 'max') if last_updated_row else None
    
    return rows, universe_count, last_updated

import json
import os

def get_custom_index_themes(market: str = "IN") -> Tuple[List[ThemeRankRecord], str]:
    """
    Dynamically calculates aggregate performance and ranking for custom indices based on screen_data momentum fields.
    Takes the JSON dictionary of Custom Indices, computes the average momentums for their constituents, and relatively ranks them.
    """
    path = os.path.join(os.path.dirname(__file__), '..', 'custom_indices_in.json')
    if not os.path.exists(path) or market.upper() != "IN":
        return [], "No Data"
        
    with open(path, 'r') as f:
        custom_indices = json.load(f)

    # Fetch all momentum data for the requested market to do fast in-memory lookups
    sql = "SELECT Ticker, Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y FROM screen_data WHERE Market = ?"
    rows = fetch_all(sql, (market,))
    
    stock_dict = {}
    for r in rows:
        t = _get(r, 'ticker', 'Ticker')
        stock_dict[t] = {
            '1d': _get(r, 'momentum_1d', 'Momentum_1D'),
            '1w': _get(r, 'momentum_1w', 'Momentum_1W'),
            '1m': _get(r, 'momentum_1m', 'Momentum_1M'),
            '3m': _get(r, 'momentum_3m', 'Momentum_3M'),
            '6m': _get(r, 'momentum_6m', 'Momentum_6M'),
            '1y': _get(r, 'momentum_1y', 'Momentum_1Y'),
        }

    index_averages = []
    
    for idx_id, info in custom_indices.items():
        name = info.get('name', idx_id)
        constituents = info.get('constituents', [])
        
        sums = {k: 0.0 for k in ['1d', '1w', '1m', '3m', '6m', '1y']}
        counts = {k: 0 for k in sums.keys()}
        valid_stocks = 0
        
        for ticker in constituents:
            if ticker in stock_dict:
                valid_stocks += 1
                for k in sums.keys():
                    val = stock_dict[ticker][k]
                    if val is not None:
                        sums[k] += float(val)
                        counts[k] += 1
                        
        if valid_stocks > 0:
            avg = {
                k: (sums[k] / counts[k]) if counts[k] > 0 else 0.0
                for k in sums.keys()
            }
            avg['id'] = idx_id
            avg['name'] = name
            avg['count'] = valid_stocks
            index_averages.append(avg)

    if not index_averages:
        return [], "No Data"

    # Compute comparative rankings (1 is highest momentum)
    # Sort and rank for each timeframe
    def rank_list(items, key):
        items.sort(key=lambda x: x[key], reverse=True)
        return {item['id']: i + 1 for i, item in enumerate(items)}

    ranks_1d = rank_list(list(index_averages), '1d')
    ranks_1w = rank_list(list(index_averages), '1w')
    ranks_1m = rank_list(list(index_averages), '1m')
    ranks_3m = rank_list(list(index_averages), '3m')
    ranks_6m = rank_list(list(index_averages), '6m')
    ranks_1y = rank_list(list(index_averages), '1y')

    results = []
    for avg in index_averages:
        idx_id = avg['id']
        r = ThemeRankRecord(
            Category="Custom Index",
            Name=avg['name'],
            Stock_Count=avg['count'],
            Rank_1D=ranks_1d[idx_id],
            Rank_1W=ranks_1w[idx_id],
            Rank_1M=ranks_1m[idx_id],
            Rank_3M=ranks_3m[idx_id],
            Rank_6M=ranks_6m[idx_id],
            Rank_1Y=ranks_1y[idx_id],
            change_1d=None,
            change_1w=None,
            change_1m=None,
            change_3m=None,
            change_6m=None,
            change_1y=None
        )
        results.append(r)
        
    # Sort the final output by Rank_1d
    results.sort(key=lambda x: x.rank_1d)

    # Get last updated date
    last_updated_row = fetch_all(f"SELECT MAX(Date) as last_date FROM screen_data WHERE Market = '{market}'")
    last_updated = _get(last_updated_row[0], 'last_date', 'max') if last_updated_row else "Unknown"

    return results, last_updated


def get_theme_proxies(category: str, name: str, limit: int = 10, market: str = "US") -> List[str]:
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
    WHERE Market = ? AND {col} = ? 
    ORDER BY (Close * RVOL) DESC NULLS LAST 
    LIMIT ?
    """
    rows = fetch_all(sql, (market, name, limit))
    
    # If the database structure makes (Close * RVOL) fail or yield nulls, fallback to RS_Rating
    if not rows:
        sql_fallback = f"""
        SELECT Ticker 
        FROM screen_data 
        WHERE Market = ? AND {col} = ? 
        ORDER BY RS_Rating DESC NULLS LAST 
        LIMIT ?
        """
        rows = fetch_all(sql_fallback, (market, name, limit))

    return [_get(r, 'ticker', 'Ticker') for r in rows if _get(r, 'ticker', 'Ticker')]
