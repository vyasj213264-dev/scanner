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

def _nan_to_none(val):
    """Convert NaN/inf to None for clean DB storage as NULL."""
    try:
        f = float(val) if not hasattr(val, 'item') else val.item()
        if pd.isna(f) or np.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None

def _safe_bool(val):
    """Convert a pandas/numpy boolean to Python bool, treating NaN as False."""
    try:
        if pd.isna(val):
            return False
        return bool(val)
    except (TypeError, ValueError):
        return False

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

# Dictionary to store daily aggregations for Stage 1-4
historical_stages = {}

def calculate_indicators(df):
    if df is None or len(df) < 5:
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

    # New Stage Analysis (Stan Weinstein 50-day SMA basis)
    df['SMA_50_Slope'] = (df['SMA_50'] / df['SMA_50'].shift(20)) - 1.0
    conditions = [
        (df['SMA_50_Slope'] > 0.01) & (df['Close'] >= df['SMA_50']),   # Stage 2: Advancing
        (df['SMA_50_Slope'] <= 0.01) & (df['Close'] >= df['SMA_50']),  # Stage 1: Basing
        (df['SMA_50_Slope'] < -0.01) & (df['Close'] < df['SMA_50']),   # Stage 4: Declining
        (df['SMA_50_Slope'] >= -0.01) & (df['Close'] < df['SMA_50'])   # Stage 3: Topping
    ]
    choices = [2, 1, 4, 3]
    df['Stage'] = np.select(conditions, choices, default=0)

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
    last_row['Stage'] = int(df['Stage'].iloc[-1])

    # Store the daily stage values into the global historical_stages dictionary
    # Only store dates where Stage is accurately calculated (> 70 rows due to 50dma + 20 slope offset)
    if len(df) > 70:
        for idx, row in df.tail(130).iterrows():
            date_str = str(idx).split(' ')[0]
            stage_val = int(row['Stage']) if pd.notna(row['Stage']) else 0
            if stage_val in [1, 2, 3, 4]:
                if date_str not in historical_stages:
                    historical_stages[date_str] = {1: 0, 2: 0, 3: 0, 4: 0}
                historical_stages[date_str][stage_val] += 1

    # NaN momentum values (due to recent IPOs) will be stored as NULL in the database
    # via _nan_to_none() during record construction — no need to fill with 0.0

    return last_row

def fetch_indian_tickers():
    import pandas as pd
    import requests
    import io
    print("Fetching Indian Tickers from NSE Master Equities List...", flush=True)
    # Replaced fragile index-specific CSVs with the comprehensive EQUITY_L list
    # This guarantees we capture NIFTY 500, Smallcap, Microcap, and SME stocks.
    urls = [
        "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    ]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/csv,application/csv'
    }
    tickers_meta = {}
    valid_tickers = []
    
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200 and 'DOCTYPE html' not in r.text:
                df = pd.read_csv(io.StringIO(r.text))
                for _, row in df.iterrows():
                    sym = str(row['SYMBOL']).strip() # EQUITY_L uses 'SYMBOL' instead of 'Symbol'
                    if sym and len(sym) <= 15 and '^' not in sym:
                        ns_sym = f"{sym}.NS"
                        if ns_sym not in tickers_meta:
                            valid_tickers.append(ns_sym)
                            tickers_meta[ns_sym] = {
                                'sector': 'Unknown',
                                'industry': 'Unknown',
                                'market_cap': None
                            }
                print(f"Successfully loaded {len(valid_tickers)} NSE equities.", flush=True)
            else:
                print(f"Fetch failed or returned HTML. Status: {r.status_code}")
        except Exception as e:
            print(f"Failed to fetch NSE list {url}: {e}", flush=True)
            
    # Inject core Indian Index Proxies for Trade Portal
    in_proxies = ['^NSEI', '^CRSMA', 'BANKNIFTY.NS', '^CNXAUTO', '^CNXIT', '^CNXMETAL', '^CNXPHARMA', '^CNXFMCG', '^CNXREALTY', '^CNXPSUBANK']
    for p in in_proxies:
        if p not in tickers_meta:
            valid_tickers.append(p)
            tickers_meta[p] = {'sector': 'Index', 'industry': 'Index', 'market_cap': None}
            
    return valid_tickers, tickers_meta

def run_ingest(market='US'):
    print(f"Loading {market} ticker universe...", flush=True)
    tickers = []
    ticker_meta = {}
    
    if market == 'US':
        # Inject core US Index Proxies for Trade Portal
        us_proxies = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLY', 'XLV', 'XLE', 'XLI', 'XLC', 'XLU', 'XLP', 'XLRE', 'XLB']
        for p in us_proxies:
            tickers.append(p)
            ticker_meta[p] = {'sector': 'Index', 'industry': 'Index', 'market_cap': None}
        
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
        except Exception as e:
            print(f"Nasdaq API failed: {e}. Falling back to SEC company tickers list...", flush=True)
            try:
                import requests
                url = 'https://www.sec.gov/files/company_tickers.json'
                headers = {'User-Agent': 'TradersChart Admin contact@example.com'}
                r = requests.get(url, headers=headers, timeout=10)
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
                
    elif market == 'IN':
        print("Fetching Indian Tickers (NSE/BSE)...", flush=True)
        in_tickers, in_meta = fetch_indian_tickers()
        tickers.extend(in_tickers)
        ticker_meta.update(in_meta)
        
        # Concurrently fetch Market Cap for Indian stocks using yfinance fast_info
        import concurrent.futures
        print("Fetching Indian Market Caps concurrently via yfinance fast_info...", flush=True)
        actual_stocks = [t for t in in_tickers if '^' not in t and 'NIFTY' not in t]
        
        def _fetch_mc(t):
            try:
                import yfinance as yf
                return t, yf.Ticker(t).fast_info.get('marketCap')
            except:
                return t, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            for t, mc in executor.map(_fetch_mc, actual_stocks):
                if mc:
                    ticker_meta[t]['market_cap'] = mc
                    
        print("Indian Market Cap fetch complete.", flush=True)

    # Remove duplicates
    tickers = list(dict.fromkeys(tickers))
    
    if os.getenv('TEST_MODE') == '1':
        print("TEST_MODE enabled: Truncating to 50 tickers...", flush=True)
        tickers = tickers[:50]

    if not tickers:
        print("Error: No tickers loaded. Exiting.", flush=True)
        return

    print(f"Running on FULL UNIVERSE: {len(tickers)} unique stocks (Note: recently IPO'd stocks < 200 days old will be bypassed due to 200-SMA requirement).", flush=True)
    
    if market == 'US' and 'SPY' not in tickers:
        tickers.append('SPY')

    # ---------------------------------------------------------
    # 2. Sequential Data Download & Indicator Calculation
    # ---------------------------------------------------------
    # We do all processing in memory FIRST to avoid keeping an idle DB connection open
    # during the long (20-30 min) yfinance download phase.
    all_data = []
    all_ohlcv = []
    chunk_size = 100
    
    benchmark_ticker = 'SPY' if market == 'US' else '^NSEI'
    print(f"Downloading benchmark ({benchmark_ticker}) for RS calculation...", flush=True)
    benchmark_data = yf.download(benchmark_ticker, period='2y', progress=False)
    
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
            print(f"  Skipping chunk {i//chunk_size + 1} after {max_retries} failed attempts. Continuing to next chunk...", flush=True)
            continue
            
        success_count = 0
        skipped_count = 0
        for ticker in chunk:
            if len(chunk) == 1:
                df = data
            else:
                try:
                    df = data[ticker].copy()
                    df.dropna(subset=['Close'], inplace=True)
                except KeyError:
                    continue
            
            if len(df) < 5:
                continue
            
            last = calculate_indicators(df)
            if last is not None:
                success_count += 1
                rs_raw = calculate_rs_rating(df, benchmark_data)
                # Convert NaN to None so PostgreSQL stores it as NULL (not NaN)
                rs_raw_clean = None if (rs_raw is None or pd.isna(rs_raw)) else float(rs_raw)
                
                try:
                    # Map indicators to the canonical order for screen_data
                    record = (
                        ticker,
                        market,
                        str(last.name),
                        _nan_to_none(last['Close']),
                        _nan_to_none(last['Volume']),
                        _nan_to_none(last['SMA_5']),
                        _nan_to_none(last['SMA_9']),
                        _nan_to_none(last['SMA_10']),
                        _nan_to_none(last['SMA_20']),
                        _nan_to_none(last['SMA_21']),
                        _nan_to_none(last['SMA_50']),
                        _nan_to_none(last['SMA_100']),
                        _nan_to_none(last['SMA_200']),
                        _nan_to_none(last['RVOL']),
                        _nan_to_none(last['ADR_20']),
                        _nan_to_none(last['Pct_From_52W_High']),
                        _safe_bool(last['In_Stage_2']),
                        _safe_bool(last['Tight_Setup']),
                        _safe_bool(last['Near_Horizontal_Resistance']),
                        rs_raw_clean,
                        _safe_bool(last['Inside_Bar']),
                        _safe_bool(last['Golden_Crossover']),
                        _safe_bool(last['Gap_Up']),
                        _safe_bool(last['Gap_Down']),
                        _safe_bool(last['VCP_Approximation']),
                        _nan_to_none(last['Momentum_1D']),
                        _nan_to_none(last['Momentum_1W']),
                        _nan_to_none(last['Momentum_1M']),
                        _nan_to_none(last['Momentum_3M']),
                        _nan_to_none(last['Momentum_6M']),
                        _nan_to_none(last['Momentum_1Y']),
                        0.0, # Placeholder for RS_Rating
                        ticker_meta.get(ticker, {}).get('sector', 'Unknown'),
                        ticker_meta.get(ticker, {}).get('industry', 'Unknown'),
                        _parse_market_cap(ticker_meta.get(ticker, {}).get('market_cap')),
                        int(last['Stage']) if pd.notna(last['Stage']) else None
                    )
                    all_data.append(record)
                    
                    # Store up to 1 year of daily trailing OHLCV data for Lightweight Charts
                    trailing_year = df.tail(252).copy()
                    
                    # yfinance uses MultiIndex columns if group_by='ticker' wasn't perfectly parsed, but here we have standard columns
                    # We need to extract Date (index), Open, High, Low, Close, Volume
                    for date_idx, row_data in trailing_year.iterrows():
                        # Handle potential numpy types / pandas timestamp
                        date_str = str(date_idx.date()) if hasattr(date_idx, 'date') else str(date_idx).split(' ')[0]
                        
                        ohlcv_record = (
                            ticker,
                            date_str,
                            _safe_float(row_data['Open']),
                            _safe_float(row_data['High']),
                            _safe_float(row_data['Low']),
                            _safe_float(row_data['Close']),
                            _safe_float(row_data['Volume'])
                        )
                        all_ohlcv.append(ohlcv_record)
                        
                except Exception as parse_e:
                    skipped_count += 1
                    continue
            else:
                skipped_count += 1

        print(f"  Chunk {i//chunk_size + 1} complete: {success_count} processed, {skipped_count} skipped. Total records: {len(all_data)}", flush=True)

    if not all_data:
        print("Error: No data records generated. Exiting.", flush=True)
        return

    # ---------------------------------------------------------
    # 2b. Download Sector ETF & Lev ETF Underlying OHLCV Data
    # ---------------------------------------------------------
    # These ETFs represent sectors in the Themes UI, or are underlying tickers
    # used by the Leveraged ETF scanner. They are NOT part of the stock
    # universe, so their OHLCV + indicator data wouldn't otherwise be computed.
    sector_etf_tickers = [
        # Sector ETFs (for Themes UI)
        'XLK', 'XLV', 'XLY', 'XLF', 'XLI', 'XLP', 'XLE', 'XLRE',
        'XLB', 'XLU', 'XLC', 'XTL', 'IYM', 'SPY',
        # Broad market ETFs (lev ETF underlyings)
        'QQQ', 'IWM', 'DIA', 'MDY', 'RSP', 'SLY',
        # Sector ETFs (lev ETF underlyings not already above)
        'SOXX', 'IBB', 'CIBR', 'SKYY', 'XRT',
        # Commodity ETFs
        'GLD', 'SLV', 'USO', 'UNG',
        # Fixed Income ETFs
        'TLT', 'IEF', 'HYG',
        # Crypto ETFs
        'IBIT', 'ETHA',
        # International ETFs
        'EEM', 'EFA', 'FXI', 'EWJ', 'EWZ',
        # Currency ETFs
        'FXY', 'FXE',
    ]
    
    # Filter out any ETFs that happen to already be in the universe
    existing_tickers = set(r[0] for r in all_ohlcv)  # ticker is first element of tuple
    etfs_to_download = [t for t in sector_etf_tickers if t not in existing_tickers]
    
    if market == 'US' and etfs_to_download:
        print(f"Downloading OHLCV for {len(etfs_to_download)} sector ETFs: {', '.join(etfs_to_download)}", flush=True)
        try:
            etf_data = yf.download(etfs_to_download, period='2y', group_by='ticker', threads=True)
            
            for etf_ticker in etfs_to_download:
                try:
                    if len(etfs_to_download) > 1:
                        df_etf = etf_data[etf_ticker].dropna(subset=['Close'])
                    else:
                        df_etf = etf_data.dropna(subset=['Close'])
                    
                    trailing = df_etf.tail(252)
                    etf_count = 0
                    for date_idx, row_data in trailing.iterrows():
                        date_str = str(date_idx.date()) if hasattr(date_idx, 'date') else str(date_idx).split(' ')[0]
                        all_ohlcv.append((
                            etf_ticker,
                            date_str,
                            _safe_float(row_data['Open']),
                            _safe_float(row_data['High']),
                            _safe_float(row_data['Low']),
                            _safe_float(row_data['Close']),
                            _safe_float(row_data['Volume'])
                        ))
                        etf_count += 1
                    
                    # ALSO compute indicators and add to screen_data (needed for Lev ETF scanner)
                    if len(df_etf) >= 5:
                        last_etf = calculate_indicators(df_etf)
                        if last_etf is not None:
                            rs_raw_etf = calculate_rs_rating(df_etf, benchmark_data)
                            rs_raw_clean_etf = None if (rs_raw_etf is None or pd.isna(rs_raw_etf)) else float(rs_raw_etf)
                            
                            etf_record = (
                                etf_ticker,
                                str(last_etf.name),
                                _nan_to_none(last_etf['Close']),
                                _nan_to_none(last_etf['Volume']),
                                _nan_to_none(last_etf['SMA_5']),
                                _nan_to_none(last_etf['SMA_9']),
                                _nan_to_none(last_etf['SMA_10']),
                                _nan_to_none(last_etf['SMA_20']),
                                _nan_to_none(last_etf['SMA_21']),
                                _nan_to_none(last_etf['SMA_50']),
                                _nan_to_none(last_etf['SMA_100']),
                                _nan_to_none(last_etf['SMA_200']),
                                _nan_to_none(last_etf['RVOL']),
                                _nan_to_none(last_etf['ADR_20']),
                                _nan_to_none(last_etf['Pct_From_52W_High']),
                                _safe_bool(last_etf['In_Stage_2']),
                                _safe_bool(last_etf['Tight_Setup']),
                                _safe_bool(last_etf['Near_Horizontal_Resistance']),
                                rs_raw_clean_etf,
                                _safe_bool(last_etf['Inside_Bar']),
                                _safe_bool(last_etf['Golden_Crossover']),
                                _safe_bool(last_etf['Gap_Up']),
                                _safe_bool(last_etf['Gap_Down']),
                                _safe_bool(last_etf['VCP_Approximation']),
                                _nan_to_none(last_etf['Momentum_1D']),
                                _nan_to_none(last_etf['Momentum_1W']),
                                _nan_to_none(last_etf['Momentum_1M']),
                                _nan_to_none(last_etf['Momentum_3M']),
                                _nan_to_none(last_etf['Momentum_6M']),
                                _nan_to_none(last_etf['Momentum_1Y']),
                                0.0, # Placeholder for RS_Rating
                                'ETF', # Sector
                                'ETF', # Industry
                                0.0, # Market Cap
                                int(last_etf['Stage']) if pd.notna(last_etf['Stage']) else None,
                                market
                            )
                            all_data.append(etf_record)
                            
                    print(f"  {etf_ticker}: {etf_count} days + indicators", flush=True)
                except Exception as etf_err:
                    print(f"  Warning: Failed to get OHLCV for {etf_ticker}: {etf_err}", flush=True)
        except Exception as etf_batch_err:
            print(f"  Warning: ETF batch download failed: {etf_batch_err}", flush=True)
    
    print(f"Total OHLCV records (stocks + ETFs): {len(all_ohlcv):,}", flush=True)

    # ---------------------------------------------------------
    # 3. Database Connection & Schema Initialization
    # ---------------------------------------------------------
    # ONLY connect right before we are ready to write.
    print(f"Opening database connection for final insertion phase...", flush=True)
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        import psycopg2
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1) if DATABASE_URL.startswith("postgres://") else DATABASE_URL
        conn = psycopg2.connect(url, connect_timeout=10)
        full_placeholders = ', '.join(['%s'] * 35)
        sql_types = {
            "TEXT PRIMARY KEY": "VARCHAR(255) PRIMARY KEY",
            "TEXT": "VARCHAR(255)", 
            "REAL": "DOUBLE PRECISION",
            "BOOLEAN": "BOOLEAN",
            "INTEGER": "INTEGER"
        }
    else:
        conn = sqlite3.connect(DB_NAME)
        full_placeholders = ', '.join(['?'] * 35)
        sql_types = {
            "TEXT PRIMARY KEY": "TEXT PRIMARY KEY",
            "TEXT": "TEXT", 
            "REAL": "REAL",
            "BOOLEAN": "BOOLEAN",
            "INTEGER": "INTEGER"
        }
    
    cursor = conn.cursor()
    
    # Drop and re-create schema to ensure freshness
    print("Re-initializing database schema...", flush=True)
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS screen_data (
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
            Market_Cap {sql_types["REAL"]},
            Stage {sql_types["INTEGER"]},
            Market {sql_types["TEXT"]}
        )
    ''')
    
    # Defensive schema migration for PostgreSQL to append missing Market column dynamically
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        # Check if Market column exists in industry_ranks
        try:
            cursor.execute("SELECT Market FROM industry_ranks LIMIT 1")
        except Exception:
            conn.rollback()
            print("Migrating industry_ranks to include Market column...", flush=True)
            try:
                cursor.execute("ALTER TABLE industry_ranks ADD COLUMN Market VARCHAR(255) DEFAULT 'US'")
                cursor.execute("ALTER TABLE industry_ranks DROP CONSTRAINT IF EXISTS industry_ranks_pkey")
                cursor.execute("ALTER TABLE industry_ranks ADD PRIMARY KEY (Date, Market, Category, Name)")
                conn.commit()
                print("Successfully migrated Postgres industry_ranks schema.", flush=True)
            except Exception as e:
                conn.rollback()
                print(f"Warning: industry_ranks migration failed: {e}. Dropping and recreating.", flush=True)
                cursor.execute("DROP TABLE IF EXISTS industry_ranks")
                conn.commit()

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS industry_ranks (
            Date {sql_types["TEXT"]},
            Market {sql_types["TEXT"]} DEFAULT 'US',
            Category {sql_types["TEXT"]},
            Name {sql_types["TEXT"]},
            Stock_Count INTEGER,
            Rank_1D INTEGER,
            Rank_1W INTEGER,
            Rank_1M INTEGER,
            Rank_3M INTEGER,
            Rank_6M INTEGER,
            Rank_1Y INTEGER,
            PRIMARY KEY (Date, Market, Category, Name)
        )
    ''')
    
    # Defensive migration for market breadth
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        try:
            cursor.execute("ALTER TABLE market_breadth_history DROP CONSTRAINT IF EXISTS market_breadth_history_pkey CASCADE")
            cursor.execute("ALTER TABLE market_breadth_history ADD PRIMARY KEY (Date, Market)")
            conn.commit()
        except:
            conn.rollback()

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS daily_ohlcv (
            Ticker {sql_types["TEXT"]},
            Market {sql_types["TEXT"]} DEFAULT 'US',
            Date {sql_types["TEXT"]},
            Open {sql_types["REAL"]},
            High {sql_types["REAL"]},
            Low {sql_types["REAL"]},
            Close {sql_types["REAL"]},
            Volume {sql_types["REAL"]},
            PRIMARY KEY (Ticker, Date)
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS scanner_results (
            scanner_id {sql_types["TEXT"]},
            Ticker {sql_types["TEXT"]},
            Market {sql_types["TEXT"]} DEFAULT 'US',
            UNIQUE(scanner_id, Ticker, Market)
        )
    ''')
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS market_breadth_history (
            Date {sql_types["TEXT"]},
            Market {sql_types["TEXT"]} DEFAULT 'US',
            Stage_1 {sql_types["INTEGER"]},
            Stage_2 {sql_types["INTEGER"]},
            Stage_3 {sql_types["INTEGER"]},
            Stage_4 {sql_types["INTEGER"]},
            PRIMARY KEY (Date, Market)
        )
    ''')

    if not (DATABASE_URL and DATABASE_URL.startswith("postgres")):
        cursor.execute("PRAGMA synchronous = OFF")
        cursor.execute("PRAGMA journal_mode = MEMORY")

    SCREEN_DATA_COLS = [
        "Ticker", "Market", "Date", "Close", "Volume", "SMA_5", "SMA_9", "SMA_10", "SMA_20", "SMA_21", "SMA_50", "SMA_100", "SMA_200",
        "RVOL", "ADR_20", "Pct_From_52W_High", "In_Stage_2", "Tight_Setup", "Near_Horizontal_Resistance", 
        "RS_Raw", "Inside_Bar", "Golden_Crossover", "Gap_Up", "Gap_Down", "VCP_Approximation", 
        "Momentum_1D", "Momentum_1W", "Momentum_1M", "Momentum_3M", "Momentum_6M", "Momentum_1Y", "RS_Rating",
        "Sector", "Industry", "Market_Cap", "Stage"
    ]
    col_str = ", ".join(SCREEN_DATA_COLS)
    placeholders = ", ".join(['%s'] * len(SCREEN_DATA_COLS)) if (DATABASE_URL and DATABASE_URL.startswith("postgres")) else ", ".join(['?'] * len(SCREEN_DATA_COLS))

    # Before inserting, selectively clear existing data for the current market
    print(f"[{market}] Clearing existing target database records...", flush=True)
    cursor.execute(f"DELETE FROM screen_data WHERE Market = '{market}'")
    cursor.execute(f"DELETE FROM daily_ohlcv WHERE Market = '{market}'")
    cursor.execute(f"DELETE FROM scanner_results WHERE Market = '{market}'")
    cursor.execute(f"DELETE FROM market_breadth_history WHERE Market = '{market}'")
    conn.commit()

    print(f"Inserting {len(all_data)} stock records into screen_data...", flush=True)
    batch_size = 500
    for i in range(0, len(all_data), batch_size):
        batch = all_data[i:i + batch_size]
        cursor.executemany(f'''
            INSERT INTO screen_data ({col_str}) VALUES ({placeholders})
        ''', batch)
        conn.commit()  # Periodically commit to keep transactions small
        print(f"  ...inserted batch {i//batch_size + 1}", flush=True)

    print(f"Successfully inserted {len(all_data)} records into screen_data.", flush=True)

    # Insert historical stages
    print(f"Aggregating {len(historical_stages)} days of historical market breadth...", flush=True)
    history_records = []
    
    # Sort dates chronologically
    sorted_dates = sorted(list(historical_stages.keys()))
    for d in sorted_dates:
        counts = historical_stages[d]
        history_records.append((
            d, counts[1], counts[2], counts[3], counts[4]
        ))
    
    if history_records:
        history_placeholders = ', '.join(['%s' if DATABASE_URL and DATABASE_URL.startswith("postgres") else '?'] * 5)
        cursor.executemany(f'''
            INSERT INTO market_breadth_history (Date, Stage_1, Stage_2, Stage_3, Stage_4, Market) 
            VALUES ({(("%s, " if DATABASE_URL and DATABASE_URL.startswith("postgres") else "?, ") + ', '.join(history_placeholders.split(', ')[1:]))}, '{market}')
        ''', history_records)
        conn.commit()
        print(f"Successfully inserted {len(history_records)} historical breadth records.", flush=True)
    
    print(f"Inserting {len(all_ohlcv)} historical quotes into daily_ohlcv...", flush=True)
    
    is_pg = DATABASE_URL and DATABASE_URL.startswith("postgres")
    ohlcv_batch_size = 10000 if is_pg else 5000
    commit_every = 50000  # commit once every 50K rows
    
    if is_pg:
        from psycopg2.extras import execute_values
        sql = '''
            INSERT INTO daily_ohlcv (Ticker, Date, Open, High, Low, Close, Volume, Market) 
            VALUES %s 
            ON CONFLICT (Ticker, Date) DO UPDATE SET 
                Market = EXCLUDED.Market,
                Open = EXCLUDED.Open, High = EXCLUDED.High, Low = EXCLUDED.Low, 
                Close = EXCLUDED.Close, Volume = EXCLUDED.Volume
        '''
        for i in range(0, len(all_ohlcv), ohlcv_batch_size):
            batch = all_ohlcv[i:i + ohlcv_batch_size]
            batch_with_market = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], market) for r in batch]
            execute_values(cursor, sql, batch_with_market, page_size=ohlcv_batch_size)
            if (i + ohlcv_batch_size) % commit_every < ohlcv_batch_size:
                conn.commit()
                print(f"  ...inserted {min(i + ohlcv_batch_size, len(all_ohlcv)):,}/{len(all_ohlcv):,} OHLCV rows", flush=True)
        conn.commit()  # final commit
    else:
        sql = f'''
            INSERT OR IGNORE INTO daily_ohlcv (Ticker, Date, Open, High, Low, Close, Volume, Market) 
            VALUES (?, ?, ?, ?, ?, ?, ?, '{market}')
        '''
        for i in range(0, len(all_ohlcv), ohlcv_batch_size):
            batch = all_ohlcv[i:i + ohlcv_batch_size]
            cursor.executemany(sql, batch)
            if (i + ohlcv_batch_size) % commit_every < ohlcv_batch_size:
                conn.commit()
                print(f"  ...inserted {min(i + ohlcv_batch_size, len(all_ohlcv)):,}/{len(all_ohlcv):,} OHLCV rows", flush=True)
        conn.commit()  # final commit
        
    print(f"Successfully inserted {len(all_ohlcv):,} historical OHLCV records.", flush=True)
    
    
    print("Calculating RS_Rating from RS_Raw percentile ranks...", flush=True)
    cursor.execute(f"SELECT Ticker, RS_Raw FROM screen_data WHERE Market = '{market}' AND RS_Raw IS NOT NULL")
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
            print(f"  Updating RS_Rating batch {i//batch_size + 1} for {len(batch)} tickers...", flush=True)
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
        "minervini-cheat":        (
            "In_Stage_2 AND RS_Rating >= 70 AND RVOL < 0.85 AND VCP_Approximation "
            "AND Momentum_3M > 0.10 AND Pct_From_52W_High > -25 "
            "AND (abs(Close - SMA_10) / SMA_10 <= 0.03 OR abs(Close - SMA_20) / SMA_20 <= 0.03)"
        ),
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
        "long-term-pf":           "f.peg_ratio > 0 AND f.peg_ratio < 1.5 AND f.revenue_doubled = 1 AND d.In_Stage_2 = 1 AND d.Market_Cap >= 500",
    }
    
    baseline = "Close >= 5"
    
    cache_records = []
    for scanner_id, condition in filters.items():
        print(f"  Calculating matches for scanner: {scanner_id}...", flush=True)
        # We LEFT JOIN fundamentals_data so both technicals and fundamentals can be queried
        cursor.execute(f"SELECT d.Ticker FROM screen_data d LEFT JOIN fundamentals_data f ON d.Ticker = f.Ticker WHERE d.Market = '{market}' AND d.{baseline} AND ({condition})")
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
                cursor.executemany(f"INSERT INTO scanner_results (scanner_id, Ticker, Market) VALUES (%s, %s, '{market}')", batch)
            else:
                cursor.executemany(f"INSERT INTO scanner_results (scanner_id, Ticker, Market) VALUES (?, ?, '{market}')", batch)
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
        cursor.execute(f"SELECT Ticker, Sector, Industry, Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y FROM screen_data WHERE Market = '{market}'")
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
                print(f"    Ranking {category_name} by {met}...", flush=True)
                grouped[f'rank_{met}'] = grouped[met].rank(ascending=False, method='min').fillna(9999).astype(int)
                
            rank_data = []
            for _, r in grouped.iterrows():
                rank_data.append((
                    latest_date,
                    market,
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
                            Date, Market, Category, Name, Stock_Count, 
                            Rank_1D, Rank_1W, Rank_1M, Rank_3M, Rank_6M, Rank_1Y
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (Date, Market, Category, Name) DO UPDATE SET
                            Stock_Count = EXCLUDED.Stock_Count,
                            Rank_1D = EXCLUDED.Rank_1D, Rank_1W = EXCLUDED.Rank_1W,
                            Rank_1M = EXCLUDED.Rank_1M, Rank_3M = EXCLUDED.Rank_3M,
                            Rank_6M = EXCLUDED.Rank_6M, Rank_1Y = EXCLUDED.Rank_1Y
                    ''', batch)
                else:
                    cursor.executemany('''
                        INSERT OR REPLACE INTO industry_ranks (
                            Date, Market, Category, Name, Stock_Count, 
                            Rank_1D, Rank_1W, Rank_1M, Rank_3M, Rank_6M, Rank_1Y
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', batch)
                conn.commit()
            print(f"Calculated and inserted {len(all_theme_data)} Sector/Industry rankings.", flush=True)

    # ---------------------------------------------------------
    # Database Cleanup / Retention Policy
    # ---------------------------------------------------------
    print("Running database retention cleanup...", flush=True)
    # Delete any Industry Ranks data older than the 5 most recent trading days
    cursor.execute(f'''
        DELETE FROM industry_ranks 
        WHERE Market = '{market}' AND Date NOT IN (
            SELECT DISTINCT Date 
            FROM industry_ranks 
            WHERE Market = '{market}'
            ORDER BY Date DESC 
            LIMIT 5
        )
    ''')
    print(f"[{market}] Database cleanup complete. Historical data pruned to 5 days.", flush=True)

    conn.commit()
    if conn:
        conn.close()
        print(f"[{market}] Database connection closed.", flush=True)
    print(f"[{market}] Ingestion complete.", flush=True)

def main():
    import sys
    target_market = sys.argv[1].upper() if len(sys.argv) > 1 else 'BOTH'
    
    if target_market in ['US', 'BOTH']:
        print("\n=== STARTING US MARKET INGESTION ===", flush=True)
        run_ingest(market='US')
        
    if target_market in ['IN', 'BOTH']:
        print("\n=== STARTING INDIAN MARKET INGESTION ===", flush=True)
        run_ingest(market='IN')

if __name__ == "__main__":
    main()
