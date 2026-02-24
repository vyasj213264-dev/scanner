import yfinance as yf
import pandas as pd
import numpy as np
import sqlite3
import datetime
import os
import time

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
    try:
        with open('master_universe.txt', 'r') as f:
            tickers = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print("Error: Could not load master_universe.txt:", e)
        return

    # User wanted ALL screeners end-to-end on full universe. No slicing.
    print(f"Running on FULL UNIVERSE: {len(tickers)} stocks.")
    
    if 'SPY' not in tickers:
        tickers.append('SPY')

    chunk_size = 100
    all_data = []
    
    spy_data = yf.download('SPY', period='2y', progress=False)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Drop table to start fresh with new columns
    cursor.execute('DROP TABLE IF EXISTS screen_data')
    
    cursor.execute('''
        CREATE TABLE screen_data (
            Ticker TEXT PRIMARY KEY,
            Date TEXT,
            Close REAL,
            Volume REAL,
            SMA_10 REAL,
            SMA_20 REAL,
            SMA_50 REAL,
            SMA_100 REAL,
            SMA_200 REAL,
            RVOL REAL,
            ADR_20 REAL,
            Pct_From_52W_High REAL,
            In_Stage_2 BOOLEAN,
            Tight_Setup BOOLEAN,
            Near_Horizontal_Resistance BOOLEAN,
            RS_Raw REAL,
            Inside_Bar BOOLEAN,
            Golden_Crossover BOOLEAN,
            Gap_Up BOOLEAN,
            Gap_Down BOOLEAN,
            VCP_Approximation BOOLEAN,
            Momentum_1M REAL,
            RS_Rating REAL
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

    cursor.executemany('''
        INSERT INTO screen_data (
            Ticker, Date, Close, Volume, SMA_10, SMA_20, SMA_50, SMA_100, SMA_200,
            RVOL, ADR_20, Pct_From_52W_High, In_Stage_2, Tight_Setup, Near_Horizontal_Resistance, 
            RS_Raw, Inside_Bar, Golden_Crossover, Gap_Up, Gap_Down, VCP_Approximation, Momentum_1M, RS_Rating
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', all_data)
    
    df_db = pd.read_sql_query("SELECT Ticker, RS_Raw FROM screen_data WHERE RS_Raw IS NOT NULL", conn)
    if not df_db.empty:
        df_db['RS_Rating'] = df_db['RS_Raw'].rank(pct=True) * 99
        update_data = list(zip(df_db['RS_Rating'], df_db['Ticker']))
        cursor.executemany("UPDATE screen_data SET RS_Rating = ? WHERE Ticker = ?", update_data)
        
    conn.commit()
    conn.close()
    print("Ingestion complete. Database rebuilt with all advanced capabilities.")

if __name__ == "__main__":
    main()
