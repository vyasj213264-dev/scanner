from typing import List, Tuple
from api.database import fetch_all, fetch_val
from api.models.themes import ThemeRankRecord


def _get(row, *keys):
    """Safely extract a value from a dict trying multiple key cases."""
    for k in keys:
        if k in row:
            return row[k]
    return None


def get_themes() -> Tuple[List[ThemeRankRecord], str]:
    """
    Fetches the Sector and Industry thematic rankings from the database.
    Calculates the 1-day rank momentum (change) dynamically comparing the most recent 
    two ingestion dates directly in Python.
    """
    # Find the two most recent ingestion dates
    dates_sql = "SELECT DISTINCT Date FROM industry_ranks ORDER BY Date DESC LIMIT 2"
    dates_rows = fetch_all(dates_sql)
    
    if not dates_rows:
        return [], "No Data"
    
    latest_date = _get(dates_rows[0], 'date', 'Date')
    
    if len(dates_rows) < 2:
        # We only have one day of data, so rank momentum is zero/null
        today_sql = "SELECT * FROM industry_ranks WHERE Date = ?"
        today_rows = fetch_all(today_sql, (latest_date,))
        results = [ThemeRankRecord.model_validate(row) for row in today_rows]
        return results, latest_date

    # We have historical data to calculate Rank Movement (+/-)
    prev_date = _get(dates_rows[1], 'date', 'Date')
    
    # Fetch today's snapshot
    today_sql = "SELECT * FROM industry_ranks WHERE Date = ?"
    today_rows = fetch_all(today_sql, (latest_date,))
    
    # Fetch yesterday's snapshot to calculate 1D momentum change
    prev_sql = "SELECT * FROM industry_ranks WHERE Date = ?"
    prev_rows = fetch_all(prev_sql, (prev_date,))
    
    # Convert prev_rows into a lookup dict: {"Category_Name": row} 
    prev_dict = {}
    for r in prev_rows:
        cat = _get(r, 'category', 'Category')
        name = _get(r, 'name', 'Name')
        key = f"{cat}_{name}"
        prev_dict[key] = r

    results = []
    for r in today_rows:
        record = ThemeRankRecord.model_validate(r)
        
        # Calculate diffs
        key = f"{record.category}_{record.name}"
        if key in prev_dict:
            pr = prev_dict[key]
            
            prev_1d = _get(pr, 'rank_1d', 'Rank_1D')
            prev_1w = _get(pr, 'rank_1w', 'Rank_1W')
            prev_1m = _get(pr, 'rank_1m', 'Rank_1M')
            prev_3m = _get(pr, 'rank_3m', 'Rank_3M')
            prev_6m = _get(pr, 'rank_6m', 'Rank_6M')
            prev_1y = _get(pr, 'rank_1y', 'Rank_1Y')
            
            # Positive change means a HIGHER rank (smaller number) today
            if prev_1d is not None: record.change_1d = prev_1d - record.rank_1d
            if prev_1w is not None: record.change_1w = prev_1w - record.rank_1w
            if prev_1m is not None: record.change_1m = prev_1m - record.rank_1m
            if prev_3m is not None: record.change_3m = prev_3m - record.rank_3m
            if prev_6m is not None: record.change_6m = prev_6m - record.rank_6m
            if prev_1y is not None: record.change_1y = prev_1y - record.rank_1y
            
        results.append(record)
        
    return results, latest_date
