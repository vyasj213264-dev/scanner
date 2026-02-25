import yfinance as yf
import pandas as pd
import numpy as np
import sqlite3
import datetime
import os
import time
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
DB_NAME = "scanner.db"

def calculate_rs_rating(stock_df, spy_df):
    try:
        if len(stock_df) < 252 or len(spy_df) < 252:
            return np.nan
        stock_perf = float(stock_df['Close'].iloc[-1]) / float(stock_df['Close'].iloc[-252])
        spy_perf = float(spy_df['Close'].iloc[-1]) / float(spy_df['Close'].iloc[-252])
        return stock_perf / spy_perf
    except Exception:
        return np.nan

def calculate_indicators(df):
    if df is None or len(df) < 200:
        return None
    
    # Moving Averages
    df['SMA_10'] = df['Close'].rolling(window=10).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_100'] = df['Close'].rolling(window=100).mean()
    df['SMA_150'] = df['Close'].rolling(window=150).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    
    df['52W_High'] = df['High'].rolling(window=252).max()
    df['52W_Low'] = df['Low'].rolling(window=252).min()
    df['Pct_From_52W_High'] = ((df['Close'] - df['52W_High']) / df['52W_High']) * 100
    
    # Volume
    df['Volume_SMA_50'] = df['Volume'].rolling(window=50).mean()
    df['RVOL'] = df['Volume'] / df['Volume_SMA_50'].replace(0, np.nan)
    
    # ADR%
    df['Daily_Range_Pct'] = ((df['High'] - df['Low']) / df['Low'].replace(0, np.nan)) * 100
    df['ADR_20'] = df['Daily_Range_Pct'].rolling(window=20).mean()
    
    # Stage Analysis
    df['SMA_200_Up'] = df['SMA_200'] > df['SMA_200'].shift(20)
    df['In_Stage_2'] = (df['Close'] > df['SMA_150']) & (df['SMA_150'] > df['SMA_200']) & df['SMA_200_Up']

    # Momentum Timeframes
    # 1D = 1 day, 1W = 5 days, 1M = 21 days, 3M = 63 days, 6M = 126 days, 1Y = 252 days
    df['Momentum_1D'] = (df['Close'] / df['Close'].shift(1)) - 1.0
    df['Momentum_1W'] = (df['Close'] / df['Close'].shift(5)) - 1.0
    df['Momentum_1M'] = (df['Close'] / df['Close'].shift(21)) - 1.0
    df['Momentum_3M'] = (df['Close'] / df['Close'].shift(63)) - 1.0
    df['Momentum_6M'] = (df['Close'] / df['Close'].shift(126)) - 1.0
    df['Momentum_1Y'] = (df['Close'] / df['Close'].shift(252)) - 1.0

    # Inside Bar
    df['Inside_Bar'] = (df['High'] < df['High'].shift(1)) & (df['Low'] > df['Low'].shift(1))

    # Golden Crossover (50 SMA crosses above 200 SMA today)
    df['Golden_Crossover'] = (df['SMA_50'] > df['SMA_200']) & (df['SMA_50'].shift(1) <= df['SMA_200'].shift(1))

    # Gap Up / Down > 2% today
    gap = (df['Open'] - df['Close'].shift(1)) / df['Close'].shift(1)
    df['Gap_Up'] = gap > 0.02
    df['Gap_Down'] = gap < -0.02

    # VCP Approximation (Volatility contraction: High-Low range today is < 50% of Average 10-day range)
    avg_10d_range = df['High'].rolling(10).max() - df['Low'].rolling(10).min()
    today_range = df['High'] - df['Low']
    df['VCP_Approximation'] = (today_range < (0.3 * avg_10d_range)) & (df['Volume'] < df['Volume_SMA_50'])

    recent_closes = df['Close'].tail(4)
    min_c = recent_closes.min()
    tight_setup = ((recent_closes.max() - min_c) / min_c) < 0.02 if min_c > 0 else False

    recent_high = df['High'].tail(126).max()
    last_close = float(df['Close'].iloc[-1])
    is_at_res = (last_close >= (recent_high * 0.98)) and (last_close <= (recent_high * 1.02))

    last_row = df.iloc[-1].copy()
    last_row['Tight_Setup'] = bool(tight_setup)
    last_row['Near_Horizontal_Resistance'] = bool(is_at_res)

    # Ensure NaN momentum values (due to recent IPOs) gracefully become None/0 in the database
    for col in ['Momentum_1D', 'Momentum_1W', 'Momentum_1M', 'Momentum_3M', 'Momentum_6M', 'Momentum_1Y']:
        if pd.isna(last_row[col]):
            last_row[col] = 0.0

    return last_row

def main():
    print("Loading ticker universe...", flush=True)
    tickers = []
    
    # dynamically fetch all US equity tickers and pre-filter those >= $5 using Nasdaq Screener API
    try:
        import requests
        print("Dynamically fetching and pre-filtering all US equity tickers from Nasdaq Screener API...", flush=True)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        url = 'https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true'
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        rows = data['data']['rows']
        print(f"Successfully fetched {len(rows)} raw tickers from Nasdaq API.", flush=True)
        
        valid_dynamic = []
        for row in rows:
            try:
                # Pre-filter: only keep stocks with last sale >= $5.00
                price_str = str(row['lastsale']).replace('$', '').replace(',', '').strip()
                if price_str and float(price_str) >= 5.0:
                    symbol = str(row['symbol']).replace('.', '-').upper().strip()
                    # Filter out preferred shares (^), warrants, and dual-class shares (/) incompatible with yfinance
                    if '^' not in symbol and '/' not in symbol and '~' not in symbol:
                        if len(symbol) <= 10 and symbol not in ('-', 'CASH', 'OTHER', 'USD'):
                            valid_dynamic.append(symbol)
            except:
                pass
                
        tickers.extend(valid_dynamic)
        print(f"Successfully pre-filtered universe down to {len(valid_dynamic)} stocks trading >= $5.00.", flush=True)
    except Exception as e:
        print(f"Warning: Failed to dynamically fetch Nasdaq index: {e}", flush=True)

    # Remove duplicates
    tickers = list(dict.fromkeys(tickers))
    
    if not tickers:
        print("Error: No tickers loaded. Exiting.", flush=True)
        return

    print(f"Running on FULL UNIVERSE: {len(tickers)} unique stocks (Note: recently IPO'd stocks < 200 days old will be bypassed due to 200-SMA requirement).")
    
    if 'SPY' not in tickers:
        tickers.append('SPY')

    chunk_size = 100
    all_data = []
    
    spy_data = yf.download('SPY', period='2y', progress=False)
    
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        import psycopg2
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1) if DATABASE_URL.startswith("postgres://") else DATABASE_URL
        conn = psycopg2.connect(url)
        placeholders = ', '.join(['%s'] * 28)
        sql_types = {
            "TEXT PRIMARY KEY": "VARCHAR(255) PRIMARY KEY",
            "TEXT": "VARCHAR(255)", 
            "REAL": "DOUBLE PRECISION",
            "BOOLEAN": "BOOLEAN"
        }
    else:
        conn = sqlite3.connect(DB_NAME)
        placeholders = ', '.join(['?'] * 28)
        sql_types = {
            "TEXT PRIMARY KEY": "TEXT PRIMARY KEY",
            "TEXT": "TEXT", 
            "REAL": "REAL",
            "BOOLEAN": "BOOLEAN"
        }
    
    cursor = conn.cursor()
    
    # Drop table to start fresh with new columns
    cursor.execute('DROP TABLE IF EXISTS screen_data')
    
    cursor.execute(f'''
        CREATE TABLE screen_data (
            Ticker {sql_types["TEXT PRIMARY KEY"]},
            Date {sql_types["TEXT"]},
            Close {sql_types["REAL"]},
            Volume {sql_types["REAL"]},
            SMA_10 {sql_types["REAL"]},
            SMA_20 {sql_types["REAL"]},
            SMA_50 {sql_types["REAL"]},
            SMA_100 {sql_types["REAL"]},
            SMA_200 {sql_types["REAL"]},
            RVOL {sql_types["REAL"]},
            ADR_20 {sql_types["REAL"]},
            Pct_From_52W_High {sql_types["REAL"]},
            In_Stage_2 {sql_types["BOOLEAN"]},
            Tight_Setup {sql_types["BOOLEAN"]},
            Near_Horizontal_Resistance {sql_types["BOOLEAN"]},
            RS_Raw {sql_types["REAL"]},
            Inside_Bar {sql_types["BOOLEAN"]},
            Golden_Crossover {sql_types["BOOLEAN"]},
            Gap_Up {sql_types["BOOLEAN"]},
            Gap_Down {sql_types["BOOLEAN"]},
            VCP_Approximation {sql_types["BOOLEAN"]},
            Momentum_1D {sql_types["REAL"]},
            Momentum_1W {sql_types["REAL"]},
            Momentum_1M {sql_types["REAL"]},
            Momentum_3M {sql_types["REAL"]},
            Momentum_6M {sql_types["REAL"]},
            Momentum_1Y {sql_types["REAL"]},
            RS_Rating {sql_types["REAL"]}
        )
    ''')
    
    # ---------------------------------------------------------
    # Create the cache table for pre-computed scanner results
    # ---------------------------------------------------------
    cursor.execute('DROP TABLE IF EXISTS scanner_results')
    cursor.execute(f'''
        CREATE TABLE scanner_results (
            scanner_id {sql_types["TEXT"]},
            Ticker {sql_types["TEXT"]},
            UNIQUE(scanner_id, Ticker)
        )
    ''')
    
    # Enable faster inserts
    if not (DATABASE_URL and DATABASE_URL.startswith("postgres")):
        cursor.execute("PRAGMA synchronous = OFF")
        cursor.execute("PRAGMA journal_mode = MEMORY")
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:min(i + chunk_size, len(tickers))]
        print(f"Processing chunk {i//chunk_size + 1}/{(len(tickers)//chunk_size)+1}...", flush=True)
        
        max_retries = 3
        retry_delay = 5
        data = None
        
        for attempt in range(max_retries):
            try:
                # Add a baseline sleep to avoid hitting the API too fast
                time.sleep(5)
                # threads=False is CRITICAL for GitHub Actions otherwise Yahoo instantly rate-limits the concurrent connections
                temp_data = yf.download(chunk, period='2y', group_by='ticker', progress=False, threads=False)
                
                # yfinance sometimes returns an empty dataframe when silently rate limited
                if temp_data.empty:
                    print(f"  Attempt {attempt+1}: Received empty data (rate limit?). Sleeping {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                    
                data = temp_data
                break
            except Exception as e:
                print(f"  Attempt {attempt+1} Failed: {e}. Sleeping {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
                
        if data is None or data.empty:
            print(f"  Skipping chunk {i//chunk_size + 1} after {max_retries} failed attempts.")
            continue
            
        for ticker in chunk:
            if len(chunk) == 1:
                df = data
            else:
                try:
                    df = data[ticker].copy()
                    df.dropna(subset=['Close'], inplace=True)
                except KeyError:
                    continue
            
            if len(df) < 200:
                continue
            
            last = calculate_indicators(df)
            if last is not None:
                rs_raw = calculate_rs_rating(df, spy_data)
                
                try:
                    record = (
                        ticker,
                        str(last.name),
                        float(last['Close']),
                        float(last['Volume']),
                        float(last['SMA_10']),
                        float(last['SMA_20']),
                        float(last['SMA_50']),
                        float(last['SMA_100']),
                        float(last['SMA_200']),
                        float(last['RVOL']),
                        float(last['ADR_20']),
                        float(last['Pct_From_52W_High']),
                        bool(last['In_Stage_2']),
                        bool(last['Tight_Setup']),
                        bool(last['Near_Horizontal_Resistance']),
                        float(rs_raw),
                        bool(last['Inside_Bar']),
                        bool(last['Golden_Crossover']),
                        bool(last['Gap_Up']),
                        bool(last['Gap_Down']),
                        bool(last['VCP_Approximation']),
                        float(last['Momentum_1D']),
                        float(last['Momentum_1W']),
                        float(last['Momentum_1M']),
                        float(last['Momentum_3M']),
                        float(last['Momentum_6M']),
                        float(last['Momentum_1Y']),
                        0.0 # Placeholder for RS_Rating
                    )
                    all_data.append(record)
                except Exception as parse_e:
                    continue

    cursor.executemany(f'''
        INSERT INTO screen_data (
            Ticker, Date, Close, Volume, SMA_10, SMA_20, SMA_50, SMA_100, SMA_200,
            RVOL, ADR_20, Pct_From_52W_High, In_Stage_2, Tight_Setup, Near_Horizontal_Resistance, 
            RS_Raw, Inside_Bar, Golden_Crossover, Gap_Up, Gap_Down, VCP_Approximation, 
            Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y, RS_Rating
        ) VALUES ({placeholders})
    ''', all_data)
    
    cursor.execute("SELECT Ticker, RS_Raw FROM screen_data WHERE RS_Raw IS NOT NULL")
    rows = cursor.fetchall()
    df_db = pd.DataFrame(rows, columns=['Ticker', 'RS_Raw'])
    
    if not df_db.empty:
        df_db['RS_Rating'] = df_db['RS_Raw'].rank(pct=True) * 99
        update_data = list(zip(df_db['RS_Rating'], df_db['Ticker']))
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            cursor.executemany("UPDATE screen_data SET RS_Rating = %s WHERE Ticker = %s", update_data)
        else:
            cursor.executemany("UPDATE screen_data SET RS_Rating = ? WHERE Ticker = ?", update_data)
            
    # ---------------------------------------------------------
    # Build the Pre-Computed Scanner Cache
    # ---------------------------------------------------------
    print("Pre-computing scanner logic and caching results...")
    # These match _FILTERS from api/services/scanner_service.py exactly
    filters = {
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
    }
    
    baseline = "Close >= 5"
    
    cache_records = []
    for scanner_id, condition in filters.items():
        # SQLite uses 1/0 for booleans, Postgres correctly parses true/false mapping natively using psycopg2
        cursor.execute(f"SELECT Ticker FROM screen_data WHERE {baseline} AND ({condition})")
        matching = cursor.fetchall()
        for row in matching:
            # handle both sqlite.Row and psycopg2.extras.DictRow
            ticker_val = row['Ticker'] if 'Ticker' in row else row[0]
            cache_records.append((scanner_id, ticker_val))
            
    if cache_records:
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            cursor.executemany("INSERT INTO scanner_results (scanner_id, Ticker) VALUES (%s, %s)", cache_records)
        else:
            cursor.executemany("INSERT INTO scanner_results (scanner_id, Ticker) VALUES (?, ?)", cache_records)
            
        print(f"Pre-computed and cached {len(cache_records)} cross-reference matches across {len(filters)} scanners.")
        
    conn.commit()
    conn.close()
    print("Ingestion complete. Database rebuilt securely with dual backend support + full pre-computation cache.")

if __name__ == "__main__":
    main()
