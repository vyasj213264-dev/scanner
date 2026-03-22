import yfinance as yf
import pandas as pd
import sqlite3
import os
import time
import argparse
import concurrent.futures
from api.database import fetch_all, get_db
from api.config import DATABASE_URL

def fetch_fundamentals(ticker):
    """
    Fetches the PEG ratio and multi-year revenue growth directly from Yahoo Finance.
    Takes longer than fast_info because it requires the full `info` dictionary and `financials` dataframe.
    """
    metrics = {
        'ticker': ticker,
        'peg_ratio': None,
        'revenue_growth_3y': None,
        'revenue_doubled': False
    }
    
    try:
        t = yf.Ticker(ticker)
        
        # 1. PEG Ratio
        info = t.info
        metrics['peg_ratio'] = info.get('trailingPegRatio') or info.get('pegRatio')
        
        # 2. Revenue Growth (Doubled roughly over last 3-4 years)
        # Yahoo 'financials' dataframe usually has the last 4 years as columns. Column 0 is most recent year.
        inc = t.financials
        if inc is not None and not inc.empty and 'Total Revenue' in inc.index:
            # Extract the raw series, drop NaNs (missing years), convert to float list
            revs = inc.loc['Total Revenue'].dropna().astype(float).values
            if len(revs) >= 3:  # We need at least 3 years to measure meaningful long-term growth
                latest = revs[0]
                oldest = revs[-1]  # The oldest accessible year in the dataframe (typically year 3 or 4)
                
                if oldest and oldest > 0:
                    growth = (latest / oldest)
                    metrics['revenue_growth_3y'] = growth
                    metrics['revenue_doubled'] = True if growth >= 2.0 else False
        
    except Exception as e:
        pass # Silently fail for individual tickers to prevent entire batch from crashing

    return metrics

def run_fundamental_ingest(market='IN'):
    print(f"Starting Weekly Fundamental Extraction for {market} Market...", flush=True)

    # 1. Fetch current active tickers from our core database
    print(f"Loading '{market}' Universe from database...", flush=True)
    rows = fetch_all(f"SELECT Ticker FROM screen_data WHERE Market = '{market}'")
    tickers = [row['Ticker'] for row in rows]
    
    if not tickers:
        print(f"No tickers found in screen_data for market {market}. Run regular ingest.py first.")
        return

    if os.getenv('TEST_MODE') == '1':
        print("TEST_MODE enabled: Truncating to 50 tickers...", flush=True)
        tickers = tickers[:50]

    print(f"Found {len(tickers)} symbols. Begin fetching deep ESG/Fundamentals...", flush=True)
    
    # 2. ThreadPool fetching
    # Limit max_workers to 10 to avoid instant auto-ban from Yahoo Finance for abusive scraping.
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_t = {executor.submit(fetch_fundamentals, t): t for t in tickers}
        for i, future in enumerate(concurrent.futures.as_completed(future_to_t)):
            if i % 100 == 0:
                print(f"Processed {i}/{len(tickers)}...", flush=True)
            res = future.result()
            results.append((
                res['ticker'],
                market,
                res['peg_ratio'],
                res['revenue_growth_3y'],
                bool(res['revenue_doubled'])
            ))

    print(f"Data Extracted. Opening Transaction to { 'Postgres' if DATABASE_URL and DATABASE_URL.startswith('postgres') else 'SQLite' }", flush=True)
    
    # 3. Synchronize with Database
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Create Table if it doesn't exist
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fundamentals_data (
                    Ticker VARCHAR(255) PRIMARY KEY,
                    Market VARCHAR(50),
                    peg_ratio DOUBLE PRECISION,
                    revenue_growth_3y DOUBLE PRECISION,
                    revenue_doubled BOOLEAN,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fundamentals_data (
                    Ticker TEXT PRIMARY KEY,
                    Market TEXT,
                    peg_ratio REAL,
                    revenue_growth_3y REAL,
                    revenue_doubled BOOLEAN,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # Clear existing Market data
        cursor.execute(f"DELETE FROM fundamentals_data WHERE Market = '{market}'")
        
        # Batch insert
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            from psycopg2.extras import execute_values
            sql = "INSERT INTO fundamentals_data (Ticker, Market, peg_ratio, revenue_growth_3y, revenue_doubled) VALUES %s"
            # batch insert in psycopg2 using execute_values
            execute_values(cursor, sql, results, page_size=100)
            conn.commit()
        else:
            sql = "INSERT INTO fundamentals_data (Ticker, Market, peg_ratio, revenue_growth_3y, revenue_doubled) VALUES (?, ?, ?, ?, ?)"
            cursor.executemany(sql, results)
            conn.commit()

    print("Success: Fundamental Ingestion Complete.", flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Refresh weekly slow-updating fundamental criteria.')
    parser.add_argument('--market', type=str, default='IN', choices=['US', 'IN'], help='Market to ingest')
    args = parser.parse_args()
    
    run_fundamental_ingest(args.market)
