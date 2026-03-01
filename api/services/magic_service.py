"""
Magic service — business logic for public near real-time watchlists.
"""
import requests
import re
from typing import List, Dict, Any
from api.database import get_db, fetch_all, DATABASE_URL
from api.models.scanner import StockResult

def get_row_val(row: dict, key: str, default: Any = None) -> Any:
    """Case-insensitive dictionary lookup for DB rows."""
    if not row: return default
    if key in row: return row[key]
    # Check lowercase variant
    low_key = key.lower()
    if low_key in row: return row[low_key]
    # Check PascalCase variant if it's 'ticker'
    if key == 'ticker' and 'Ticker' in row: return row['Ticker']
    return default

def get_magic_test_data() -> List[Dict[str, Any]]:
    """
    Returns the grouped stocks in the magic watchlist with live metrics.
    Output format: [{"section": "Longs", "stocks": [StockResult, ...]}, ...]
    """
    # 1. Fetch raw items
    items = fetch_all("SELECT section, ticker, sort_order FROM magic_watchlist_items ORDER BY section, sort_order ASC")
    if not items:
        # Try to sync if empty
        sync_tradingview_watchlist()
        items = fetch_all("SELECT section, ticker, sort_order FROM magic_watchlist_items ORDER BY section, sort_order ASC")
        if not items:
            return []

    # 2. Get unique tickers to fetch metrics
    tickers = list(set([get_row_val(item, 'ticker') for item in items if get_row_val(item, 'ticker')]))
    if not tickers:
        return []
    
    # 3. Fetch metrics from screen_data
    # We join them manually to ensure we keep the section grouping
    placeholders = ",".join(["?"] * len(tickers))
    sql = f"SELECT * FROM screen_data WHERE Ticker IN ({placeholders})"
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        sql = sql.replace('?', '%s')
    
    metrics_rows = fetch_all(sql, tuple(tickers))
    metrics_map = {}
    for row in metrics_rows:
        t = get_row_val(row, 'Ticker')
        if t:
            try:
                # Ensure we pass a dict that Pydantic likes (PascalCase for aliases)
                pydantic_dict = dict(row)
                # If Ticker is lowercase, satisfy the validation_alias
                if 'ticker' in pydantic_dict and 'Ticker' not in pydantic_dict:
                    pydantic_dict['Ticker'] = pydantic_dict['ticker']
                
                metrics_map[t] = StockResult.model_validate(pydantic_dict)
            except Exception as e:
                print(f"Validation error for {t}: {e}")

    # 4. Group by section
    sections_map = {}
    for item in items:
        section = get_row_val(item, 'section', 'General')
        ticker = get_row_val(item, 'ticker')
        if not ticker: continue
        
        if section not in sections_map:
            sections_map[section] = []
        
        # If we have metrics, add them; otherwise, add a skeleton item
        if ticker in metrics_map:
            sections_map[section].append(metrics_map[ticker])
        else:
            # Placeholder for tickers not in DB yet
            sections_map[section].append({"ticker": ticker, "company": "Unknown", "price": 0, "rs_rating": 0})

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

def sync_tradingview_watchlist(watchlist_id: str = "42004254") -> bool:
    """
    Scrapes the public TradingView watchlist and updates our magic_watchlist_items table.
    """
    url = f"https://www.tradingview.com/watchlists/{watchlist_id}/"
    try:
        print(f"🔄 Syncing TradingView watchlist {watchlist_id}...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        
        # Extract JSON from <script type="application/prs.init-data+json">
        match = re.search(r'<script type=\"application/prs\.init-data\+json\">(.*?)</script>', res.text, re.DOTALL)
        if not match:
            print("❌ Could not find initialization JSON in TradingView page")
            return False
            
        data_json = json.loads(match.group(1))
        symbols_list = data_json.get("sharedWatchlist", {}).get("list", {}).get("symbols", [])
        
        if not symbols_list:
            print("❌ No symbols found in TradingView JSON")
            return False

        # Group symbols into sections
        payload = []
        current_section = "General"
        current_tickers = []
        
        for item in symbols_list:
            if item.startswith("###"):
                # Save previous section if it had tickers
                if current_tickers:
                    payload.append({"section": current_section, "tickers": current_tickers})
                # Start new section
                current_section = item.replace("###", "").strip()
                current_tickers = []
            else:
                # TradingView uses 'EXCHANGE:TICKER' format, we want just TICKER for screen_data lookup
                ticker = item.split(":")[-1] if ":" in item else item
                current_tickers.append(ticker)
        
        # Add final section
        if current_tickers:
            payload.append({"section": current_section, "tickers": current_tickers})

        # Update local DB
        update_magic_test_data(payload)
        print(f"✅ Successfully synced {len(symbols_list)} items across {len(payload)} sections")
        return True
    except Exception as e:
        print(f"❌ Sync error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
