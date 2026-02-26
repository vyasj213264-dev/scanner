from typing import List, Tuple
from api.database import fetch_all, fetch_val
from api.models.themes import ThemeRankRecord

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
        
    latest_date = dates_rows[0]['Date'] if 'Date' in dates_rows[0] else dates_rows[0][0]
    
    if len(dates_rows) < 2:
        # We only have one day of data, so rank momentum is zero/null
        today_sql = "SELECT * FROM industry_ranks WHERE Date = ?"
        today_rows = fetch_all(today_sql, (latest_date,))
        results = [ThemeRankRecord.model_validate(row) for row in today_rows]
        return results, latest_date

    # We have historical data to calculate Rank Movement (+/-)
    prev_date = dates_rows[1]['Date'] if 'Date' in dates_rows[1] else dates_rows[1][0]
    
    # Fetch today's snapshot
    today_sql = "SELECT * FROM industry_ranks WHERE Date = ?"
    today_rows = fetch_all(today_sql, (latest_date,))
    
    # Fetch yesterday's snapshot to calculate 1D momentum change
    prev_sql = "SELECT * FROM industry_ranks WHERE Date = ?"
    prev_rows = fetch_all(prev_sql, (prev_date,))
    
    # Convert prev_rows into a lookup dict: {"Category_Name": row} 
    prev_dict = {}
    for r in prev_rows:
        cat = r['Category'] if 'Category' in r else r[1]
        name = r['Name'] if 'Name' in r else r[2]
        key = f"{cat}_{name}"
        prev_dict[key] = r

    results = []
    for r in today_rows:
        record = ThemeRankRecord.model_validate(r)
        
        # Calculate diffs
        key = f"{record.category}_{record.name}"
        if key in prev_dict:
            pr = prev_dict[key]
            
            # Helper to extract rank safely from generic dict or DB row
            def g(row, field):
                return row[field] if field in row else row.get(field.lower())
                
            prev_1d = g(pr, "Rank_1D")
            prev_1w = g(pr, "Rank_1W")
            prev_1m = g(pr, "Rank_1M")
            prev_3m = g(pr, "Rank_3M")
            prev_6m = g(pr, "Rank_6M")
            prev_1y = g(pr, "Rank_1Y")
            
            # Positive change means a HIGHER rank (smaller number) today
            # Example: Yesterday Rank #10, Today Rank #5. Change = +5.
            if prev_1d is not None: record.change_1d = prev_1d - record.rank_1d
            if prev_1w is not None: record.change_1w = prev_1w - record.rank_1w
            if prev_1m is not None: record.change_1m = prev_1m - record.rank_1m
            if prev_3m is not None: record.change_3m = prev_3m - record.rank_3m
            if prev_6m is not None: record.change_6m = prev_6m - record.rank_6m
            if prev_1y is not None: record.change_1y = prev_1y - record.rank_1y
            
        results.append(record)
        
    return results, latest_date
