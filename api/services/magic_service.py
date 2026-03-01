"""
Magic service — business logic for public near real-time watchlists.
"""
from typing import List, Dict, Any
from api.database import get_db, fetch_all, DATABASE_URL
from api.models.scanner import StockResult

def get_magic_test_data() -> List[Dict[str, Any]]:
    """
    Returns the grouped stocks in the magic watchlist with live metrics.
    Output format: [{"section": "Longs", "stocks": [StockResult, ...]}, ...]
    """
    # 1. Fetch raw items
    items = fetch_all("SELECT section, ticker, sort_order FROM magic_watchlist_items ORDER BY section, sort_order ASC")
    if not items:
        return []

    # 2. Get unique tickers to fetch metrics
    tickers = list(set([item['ticker'] for item in items]))
    
    # 3. Fetch metrics from screen_data
    # We join them manually to ensure we keep the section grouping
    placeholders = ",".join(["?"] * len(tickers))
    sql = f"SELECT * FROM screen_data WHERE Ticker IN ({placeholders})"
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        sql = sql.replace('?', '%s')
    
    metrics_rows = fetch_all(sql, tuple(tickers))
    metrics_map = {row['Ticker']: StockResult.model_validate(row) for row in metrics_rows}
    
    # 4. Group by section
    sections_map = {}
    for item in items:
        section = item['section']
        ticker = item['ticker']
        if section not in sections_map:
            sections_map[section] = []
        
        # If we have metrics, add them; otherwise, add a skeleton item
        if ticker in metrics_map:
            sections_map[section].append(metrics_map[ticker])
        else:
            # Placeholder for tickers not in DB yet
            sections_map[section].append({"Ticker": ticker, "Company": "Unknown", "Price": 0, "RS_Rating": 0})

    # Convert map to list of dicts
    result = []
    # Maintain some order of sections if possible
    for section_name in sorted(sections_map.keys()):
        result.append({
            "section": section_name,
            "stocks": sections_map[section_name]
        })
    
    return result

def update_magic_test_data(payload: List[Dict[str, Any]]) -> bool:
    """
    Overwrites the current magic watchlist items.
    Payload: [{"section": "Longs", "tickers": ["AAPL", "MSFT"]}, ...]
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Clear existing
        cursor.execute("DELETE FROM magic_watchlist_items")
        
        # 2. Insert new
        sql = "INSERT INTO magic_watchlist_items (section, ticker, sort_order) VALUES (?, ?, ?)"
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            sql = sql.replace('?', '%s')
            
        insert_data = []
        for section_data in payload:
            section = section_data.get("section", "General")
            tickers = section_data.get("tickers", [])
            for idx, ticker in enumerate(tickers):
                insert_data.append((section, ticker.upper(), idx))
        
        if insert_data:
            cursor.executemany(sql, insert_data)
        
        conn.commit()
    return True
