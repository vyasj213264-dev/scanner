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

    # Momentum 1 Month
    df['Momentum_1M'] = (df['Close'] / df['Close'].shift(21)) - 1.0

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

    return last_row

def main():
    print("Loading ticker universe...")
    tickers = []
    
    # Attempt to load custom tickers from file FIRST
    try:
        with open('master_universe.txt', 'r') as f:
            custom_tickers = [line.strip().upper() for line in f if line.strip()]
            tickers.extend(custom_tickers)
            print(f"Loaded {len(custom_tickers)} custom tickers from master_universe.txt")
    except Exception as e:
        print("Note: Could not load master_universe.txt:", e)

    # dynamically fetch index components
    try:
        import requests
        import io
        print("Dynamically fetching S&P 500, Nasdaq 100, and Russell 2000 tickers...")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        # S&P 500
        r_sp = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers)
        sp500 = pd.read_html(io.StringIO(r_sp.text))[0]['Symbol'].tolist()
        
        # Nasdaq 100
        r_ndx = requests.get('https://en.wikipedia.org/wiki/Nasdaq-100', headers=headers)
        ndx = pd.read_html(io.StringIO(r_ndx.text))[4]['Ticker'].tolist()
        
        # Russell 2000 (from iShares IWM ETF CSV)
        r_iwm = requests.get('https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund', headers=headers)
        r2k_df = pd.read_csv(io.StringIO(r_iwm.text), skiprows=9)
        r2k = r2k_df['Ticker'].dropna().tolist()
        
        dynamic_tickers = sp500 + ndx + r2k
        valid_dynamic = [str(t).replace('.', '-').upper() for t in dynamic_tickers if isinstance(t, str) and t not in ('-', 'Cash', 'Other', 'USD')]
        tickers.extend(valid_dynamic)
        print(f"Successfully fetched {len(valid_dynamic)} index components.")
    except Exception as e:
        print(f"Warning: Failed to dynamically fetch indexes: {e}")

    # Remove duplicates
    tickers = list(dict.fromkeys(tickers))
    
    if not tickers:
        print("Error: No tickers loaded. Exiting.")
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
        placeholders = ', '.join(['%s'] * 23)
        sql_types = {
            "TEXT PRIMARY KEY": "VARCHAR(255) PRIMARY KEY",
            "TEXT": "VARCHAR(255)", 
            "REAL": "DOUBLE PRECISION",
            "BOOLEAN": "BOOLEAN"
        }
    else:
        conn = sqlite3.connect(DB_NAME)
        placeholders = ', '.join(['?'] * 23)
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
            Momentum_1M {sql_types["REAL"]},
            RS_Rating {sql_types["REAL"]}
        )
    ''')
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:min(i + chunk_size, len(tickers))]
        print(f"Processing chunk {i//chunk_size + 1}/{(len(tickers)//chunk_size)+1}...")
        
        try:
            data = yf.download(chunk, period='2y', group_by='ticker', progress=False, threads=True)
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
                            float(last['Momentum_1M']),
                            0.0 # Placeholder for RS_Rating
                        )
                        all_data.append(record)
                    except Exception as parse_e:
                        continue
        except Exception as e:
            time.sleep(2)

    cursor.executemany(f'''
        INSERT INTO screen_data (
            Ticker, Date, Close, Volume, SMA_10, SMA_20, SMA_50, SMA_100, SMA_200,
            RVOL, ADR_20, Pct_From_52W_High, In_Stage_2, Tight_Setup, Near_Horizontal_Resistance, 
            RS_Raw, Inside_Bar, Golden_Crossover, Gap_Up, Gap_Down, VCP_Approximation, Momentum_1M, RS_Rating
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
        
    conn.commit()
    conn.close()
    print("Ingestion complete. Database rebuilt securely with dual backend support.")

if __name__ == "__main__":
    main()
