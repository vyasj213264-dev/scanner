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

_rs_error_logged = False  # Only log the first RS error to avoid spamming logs

def _parse_market_cap(val):
    """Parse Nasdaq API market cap string to float. Returns None if unparseable."""
    if val is None:
        return None
    try:
        # Nasdaq API returns marketCap as a numeric string or int
        return float(str(val).replace(',', '').strip())
    except (ValueError, TypeError):
        return None

def _safe_float(val):
    """Safely extract a Python float from a pandas scalar, Series, or numpy type."""
    if hasattr(val, 'item'):
        return val.item()  # handles numpy scalars and single-element Series
    return float(val)

def calculate_rs_rating(stock_df, spy_df):
    global _rs_error_logged
    try:
        if len(stock_df) < 252 or len(spy_df) < 252:
            return np.nan
        stock_perf = _safe_float(stock_df['Close'].iloc[-1]) / _safe_float(stock_df['Close'].iloc[-252])
        spy_perf = _safe_float(spy_df['Close'].iloc[-1]) / _safe_float(spy_df['Close'].iloc[-252])
        return stock_perf / spy_perf
    except Exception as e:
        if not _rs_error_logged:
            print(f"WARNING: calculate_rs_rating failed: {type(e).__name__}: {e}", flush=True)
            _rs_error_logged = True
        return np.nan

def calculate_indicators(df):
    if df is None or len(df) < 200:
        return None
    
    # Moving Averages
    df['SMA_5'] = df['Close'].rolling(window=5).mean()
    df['SMA_9'] = df['Close'].rolling(window=9).mean()
    df['SMA_10'] = df['Close'].rolling(window=10).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_21'] = df['Close'].rolling(window=21).mean()
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
    ticker_meta = {} # Dict to store {ticker: {'sector': '...', 'industry': '...'}}
    
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
                            # Save Sector and Industry for thematic ranking later
                            sector = str(row.get('sector', '')).strip()
                            industry = str(row.get('industry', '')).strip()
                            ticker_meta[symbol] = {
                                'sector': sector if sector else 'Unknown',
                                'industry': industry if industry else 'Unknown',
                                'market_cap': row.get('marketCap', None)
                            }
            except:
                pass
                
        tickers.extend(valid_dynamic)
        print(f"Successfully pre-filtered universe down to {len(valid_dynamic)} stocks trading >= $5.00.", flush=True)
    except Exception as e:
        print(f"Warning: Failed to dynamically fetch Nasdaq index: {e}", flush=True)
        print("Falling back to SEC company tickers list...", flush=True)
        try:
            sec_url = 'https://www.sec.gov/files/company_tickers.json'
            r = requests.get(sec_url, headers={'User-Agent': 'TradersChart admin@traderschart.com'}, timeout=10)
            r.raise_for_status()
            data = r.json()
            # Returns dict like: {"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}}
            valid_fallback = []
            for item in data.values():
                symbol = str(item.get('ticker', '')).replace('.', '-').upper().strip()
                if symbol and '^' not in symbol and '/' not in symbol and '~' not in symbol:
                    if len(symbol) <= 6 and symbol not in ('-', 'CASH', 'OTHER', 'USD'):
                        valid_fallback.append(symbol)
                        ticker_meta[symbol] = {
                            'sector': 'Unknown',
                            'industry': 'Unknown',
                            'market_cap': None
                        }
            tickers.extend(valid_fallback)
            print(f"Successfully loaded {len(valid_fallback)} symbols from SEC fallback.", flush=True)
        except Exception as sec_e:
            print(f"Error: SEC fallback also failed: {sec_e}", flush=True)

    # Remove duplicates
    tickers = list(dict.fromkeys(tickers))
    
    if os.getenv('TEST_MODE') == '1':
        print("TEST_MODE enabled: Truncating to 50 tickers...", flush=True)
        tickers = tickers[:50]

    if not tickers:
        print("Error: No tickers loaded. Exiting.", flush=True)
        return

    print(f"Running on FULL UNIVERSE: {len(tickers)} unique stocks (Note: recently IPO'd stocks < 200 days old will be bypassed due to 200-SMA requirement).", flush=True)
    
    if 'SPY' not in tickers:
        tickers.append('SPY')

    # ---------------------------------------------------------
    # 2. Sequential Data Download & Indicator Calculation
    # ---------------------------------------------------------
    # We do all processing in memory FIRST to avoid keeping an idle DB connection open
    # during the long (20-30 min) yfinance download phase.
    all_data = []
    chunk_size = 100
    
    spy_data = yf.download('SPY', period='2y', progress=False)
    
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
                    print(f"  Attempt {attempt+1}: Received empty data (rate limit?). Sleeping {retry_delay}s...", flush=True)
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                    
                data = temp_data
                break
            except Exception as e:
                print(f"  Attempt {attempt+1} Failed: {e}. Sleeping {retry_delay}s...", flush=True)
                time.sleep(retry_delay)
                retry_delay *= 2
                
        if data is None or data.empty:
            print(f"  Skipping chunk {i//chunk_size + 1} after {max_retries} failed attempts.", flush=True)
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
                # Convert NaN to None so PostgreSQL stores it as NULL (not NaN)
                rs_raw_clean = None if (rs_raw is None or pd.isna(rs_raw)) else float(rs_raw)
                
                try:
                    record = (
                        ticker,
                        str(last.name),
                        float(last['Close']),
                        float(last['Volume']),
                        float(last['SMA_5']),
                        float(last['SMA_9']),
                        float(last['SMA_10']),
                        float(last['SMA_20']),
                        float(last['SMA_21']),
                        float(last['SMA_50']),
                        float(last['SMA_100']),
                        float(last['SMA_200']),
                        float(last['RVOL']),
                        float(last['ADR_20']),
                        float(last['Pct_From_52W_High']),
                        bool(last['In_Stage_2']),
                        bool(last['Tight_Setup']),
                        bool(last['Near_Horizontal_Resistance']),
                        rs_raw_clean,
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
                        0.0, # Placeholder for RS_Rating
                        ticker_meta.get(ticker, {}).get('sector', 'Unknown'),
                        ticker_meta.get(ticker, {}).get('industry', 'Unknown'),
                        _parse_market_cap(ticker_meta.get(ticker, {}).get('market_cap'))
                    )
                    all_data.append(record)
                except Exception as parse_e:
                    continue

    if not all_data:
        print("Error: No data records generated. Exiting.", flush=True)
        return

    # ---------------------------------------------------------
    # 3. Database Connection & Schema Initialization
    # ---------------------------------------------------------
    # ONLY connect right before we are ready to write.
    print(f"Opening database connection for final insertion phase...", flush=True)
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        import psycopg2
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1) if DATABASE_URL.startswith("postgres://") else DATABASE_URL
        conn = psycopg2.connect(url, connect_timeout=10)
        full_placeholders = ', '.join(['%s'] * 34)
        sql_types = {
            "TEXT PRIMARY KEY": "VARCHAR(255) PRIMARY KEY",
            "TEXT": "VARCHAR(255)", 
            "REAL": "DOUBLE PRECISION",
            "BOOLEAN": "BOOLEAN"
        }
    else:
        conn = sqlite3.connect(DB_NAME)
        full_placeholders = ', '.join(['?'] * 34)
        sql_types = {
            "TEXT PRIMARY KEY": "TEXT PRIMARY KEY",
            "TEXT": "TEXT", 
            "REAL": "REAL",
            "BOOLEAN": "BOOLEAN"
        }
    
    cursor = conn.cursor()
    
    # Drop and re-create schema to ensure freshness
    print("Re-initializing database schema...", flush=True)
    cursor.execute('DROP TABLE IF EXISTS screen_data')
    cursor.execute(f'''
        CREATE TABLE screen_data (
            Ticker {sql_types["TEXT PRIMARY KEY"]},
            Date {sql_types["TEXT"]},
            Close {sql_types["REAL"]},
            Volume {sql_types["REAL"]},
            SMA_5 {sql_types["REAL"]},
            SMA_9 {sql_types["REAL"]},
            SMA_10 {sql_types["REAL"]},
            SMA_20 {sql_types["REAL"]},
            SMA_21 {sql_types["REAL"]},
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
            RS_Rating {sql_types["REAL"]},
            Sector {sql_types["TEXT"]},
            Industry {sql_types["TEXT"]},
            Market_Cap {sql_types["REAL"]}
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS industry_ranks (
            Date {sql_types["TEXT"]},
            Category {sql_types["TEXT"]},
            Name {sql_types["TEXT"]},
            Stock_Count INTEGER,
            Rank_1D INTEGER,
            Rank_1W INTEGER,
            Rank_1M INTEGER,
            Rank_3M INTEGER,
            Rank_6M INTEGER,
            Rank_1Y INTEGER,
            PRIMARY KEY (Date, Category, Name)
        )
    ''')
    
    cursor.execute('DROP TABLE IF EXISTS scanner_results')
    cursor.execute(f'''
        CREATE TABLE scanner_results (
            scanner_id {sql_types["TEXT"]},
            Ticker {sql_types["TEXT"]},
            UNIQUE(scanner_id, Ticker)
        )
    ''')
    
    if not (DATABASE_URL and DATABASE_URL.startswith("postgres")):
        cursor.execute("PRAGMA synchronous = OFF")
        cursor.execute("PRAGMA journal_mode = MEMORY")

    # ---------------------------------------------------------
    # 4. Final Batch Insertions
    # ---------------------------------------------------------
    print(f"Inserting {len(all_data)} stock records into screen_data...", flush=True)
    batch_size = 500
    for i in range(0, len(all_data), batch_size):
        batch = all_data[i:i + batch_size]
        cursor.executemany(f'''
            INSERT INTO screen_data (
                Ticker, Date, Close, Volume, SMA_5, SMA_9, SMA_10, SMA_20, SMA_21, SMA_50, SMA_100, SMA_200,
                RVOL, ADR_20, Pct_From_52W_High, In_Stage_2, Tight_Setup, Near_Horizontal_Resistance, 
                RS_Raw, Inside_Bar, Golden_Crossover, Gap_Up, Gap_Down, VCP_Approximation, 
                Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y, RS_Rating,
                Sector, Industry, Market_Cap
            ) VALUES ({full_placeholders})
        ''', batch)
        conn.commit()  # Periodically commit to keep transactions small
        print(f"  ...inserted batch {i//batch_size + 1}", flush=True)

    print(f"Successfully inserted {len(all_data)} records.", flush=True)
    
    
    print("Calculating RS_Rating from RS_Raw percentile ranks...", flush=True)
    cursor.execute("SELECT Ticker, RS_Raw FROM screen_data WHERE RS_Raw IS NOT NULL")
    rows = cursor.fetchall()
    # Handle list of tuples directly (default for both sqlite3 and psycopg2 without DictRow)
    df_db = pd.DataFrame(rows, columns=['Ticker', 'RS_Raw'])
    # Extra safety: drop any NaN values that slipped through
    df_db = df_db.dropna(subset=['RS_Raw'])
    
    print(f"Found {len(df_db)} tickers with valid RS_Raw values.", flush=True)
    
    if not df_db.empty:
        df_db['RS_Rating'] = df_db['RS_Raw'].rank(pct=True) * 99
        update_data = [(float(r), t) for r, t in zip(df_db['RS_Rating'], df_db['Ticker'])]
        
        for i in range(0, len(update_data), batch_size):
            batch = update_data[i:i + batch_size]
            if DATABASE_URL and DATABASE_URL.startswith("postgres"):
                cursor.executemany("UPDATE screen_data SET RS_Rating = %s WHERE Ticker = %s", batch)
            else:
                cursor.executemany("UPDATE screen_data SET RS_Rating = ? WHERE Ticker = ?", batch)
            conn.commit()
        
        print(f"Successfully updated RS_Rating for {len(update_data)} tickers.", flush=True)
            
    # ---------------------------------------------------------
    # Build the Pre-Computed Scanner Cache
    # ---------------------------------------------------------
    print("Pre-computing scanner logic and caching results...", flush=True)
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
        "pullback-5dma":          "abs(Close - SMA_5) / SMA_5 <= 0.02",
        "pullback-9dma":          "abs(Close - SMA_9) / SMA_9 <= 0.02",
        "pullback-21dma":         "abs(Close - SMA_21) / SMA_21 <= 0.02",
        "pullback-50dma":         "abs(Close - SMA_50) / SMA_50 <= 0.02",
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
        batch_size = 500
        for i in range(0, len(cache_records), batch_size):
            batch = cache_records[i:i + batch_size]
            if DATABASE_URL and DATABASE_URL.startswith("postgres"):
                cursor.executemany("INSERT INTO scanner_results (scanner_id, Ticker) VALUES (%s, %s)", batch)
            else:
                cursor.executemany("INSERT INTO scanner_results (scanner_id, Ticker) VALUES (?, ?)", batch)
            conn.commit()
            
        print(f"Pre-computed and cached {len(cache_records)} cross-reference matches across {len(filters)} scanners.", flush=True)
        
    # ---------------------------------------------------------
    # Build the Industry/Theme Ranks
    # ---------------------------------------------------------
    print("Calculating Sector and Industry rankings...", flush=True)
    # Fetch today's date from the just-inserted screen_data
    cursor.execute("SELECT MAX(Date) FROM screen_data")
    latest_date_tuple = cursor.fetchone()
    
    if latest_date_tuple and latest_date_tuple[0]:
        latest_date = latest_date_tuple[0]
        # Load all momentums with their Sector/Industry
        cursor.execute("SELECT Ticker, Sector, Industry, Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y FROM screen_data")
        theme_rows = cursor.fetchall()
        
        # Direct conversion to pandas. Handles both SQLite tuples and psycopg2 DictRows efficiently.
        theme_df = pd.DataFrame(theme_rows, columns=['Ticker', 'Sector', 'Industry', 'm1d', 'm1w', 'm1m', 'm3m', 'm6m', 'm1y'])
        
        # Helper to group, calculate median, rank, and format for DB
        def generate_ranks(df, group_col, category_name):
            # Only rank legitimate groups (filter out 'Unknown' or empty)
            valid_df = df[(df[group_col] != 'Unknown') & (df[group_col] != '')]
            if valid_df.empty: return []
            
            # Median momentum across the group
            grouped = valid_df.groupby(group_col).agg({
                'Ticker': 'count',
                'm1d': 'median', 'm1w': 'median', 'm1m': 'median',
                'm3m': 'median', 'm6m': 'median', 'm1y': 'median'
            }).reset_index()
            
            # Rank (ascending=False means highest momentum gets rank 1)
            # method='min' ensures ties get the same top rank
            for met in ['m1d', 'm1w', 'm1m', 'm3m', 'm6m', 'm1y']:
                grouped[f'rank_{met}'] = grouped[met].rank(ascending=False, method='min').fillna(9999).astype(int)
                
            rank_data = []
            for _, r in grouped.iterrows():
                rank_data.append((
                    latest_date,
                    category_name,
                    str(r[group_col]),
                    int(r['Ticker']),
                    int(r['rank_m1d']),
                    int(r['rank_m1w']),
                    int(r['rank_m1m']),
                    int(r['rank_m3m']),
                    int(r['rank_m6m']),
                    int(r['rank_m1y'])
                ))
            return rank_data
            
        sector_ranks = generate_ranks(theme_df, 'Sector', 'Sector')
        industry_ranks = generate_ranks(theme_df, 'Industry', 'Industry')
        all_theme_data = sector_ranks + industry_ranks
        
        if all_theme_data:
            batch_size = 500
            for i in range(0, len(all_theme_data), batch_size):
                batch = all_theme_data[i:i + batch_size]
                if DATABASE_URL and DATABASE_URL.startswith("postgres"):
                    cursor.executemany('''
                        INSERT INTO industry_ranks (
                            Date, Category, Name, Stock_Count, 
                            Rank_1D, Rank_1W, Rank_1M, Rank_3M, Rank_6M, Rank_1Y
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (Date, Category, Name) DO UPDATE SET
                            Stock_Count = EXCLUDED.Stock_Count,
                            Rank_1D = EXCLUDED.Rank_1D, Rank_1W = EXCLUDED.Rank_1W,
                            Rank_1M = EXCLUDED.Rank_1M, Rank_3M = EXCLUDED.Rank_3M,
                            Rank_6M = EXCLUDED.Rank_6M, Rank_1Y = EXCLUDED.Rank_1Y
                    ''', batch)
                else:
                    cursor.executemany('''
                        INSERT OR REPLACE INTO industry_ranks (
                            Date, Category, Name, Stock_Count, 
                            Rank_1D, Rank_1W, Rank_1M, Rank_3M, Rank_6M, Rank_1Y
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', batch)
                conn.commit()
            print(f"Calculated and inserted {len(all_theme_data)} Sector/Industry rankings.", flush=True)

    # ---------------------------------------------------------
    # Database Cleanup / Retention Policy
    # ---------------------------------------------------------
    print("Running database retention cleanup...", flush=True)
    # Delete any Industry Ranks data older than the 5 most recent trading days
    cursor.execute('''
        DELETE FROM industry_ranks 
        WHERE Date NOT IN (
            SELECT DISTINCT Date 
            FROM industry_ranks 
            ORDER BY Date DESC 
            LIMIT 5
        )
    ''')
    print("Database cleanup complete. Historical data pruned to 5 days.", flush=True)

    conn.commit()
    if conn:
        conn.close()
        print("Database connection closed.", flush=True)
    print("Ingestion complete. Database rebuilt securely with dual backend support + full pre-computation cache.", flush=True)

if __name__ == "__main__":
    main()
