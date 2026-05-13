import yfinance as yf
import pandas as pd
import numpy as np
import sqlite3
import datetime
import os
import time
from dotenv import load_dotenv

load_dotenv()
import json as _json

# Configurable historic data retention period (e.g. '5y', '10y', 'max')
HISTORY_PERIOD = os.environ.get('HISTORY_PERIOD', '5y')
DATABASE_URL = os.getenv("DATABASE_URL")
DB_NAME = "scanner.db"

_rs_error_logged = False  # Only log the first RS error to avoid spamming logs

# ── IBD Industry → ETF Proxy Mapping ──────────────────────────────────────
# Maps Yahoo Finance industry names to the best IBD industry ETF ticker.
# This is the parallel classification system — separate from Yahoo Finance sectors.
INDUSTRY_TO_ETF = {
    # ── TECHNOLOGY ──
    'Semiconductors': 'SMH', 'Semiconductor Equipment & Materials': 'SMH',
    'Semiconductor Memory': 'SMH', 'Fabless Semiconductors': 'SMH',
    'Software—Application': 'IGV', 'Software—Infrastructure': 'IGV',
    'Software - Application': 'IGV', 'Software - Infrastructure': 'IGV',
    'Information Technology Services': 'IGV', 'Electronic Components': 'SMH',
    'Scientific & Technical Instruments': 'SMH',
    'Computer Hardware': 'XLK', 'Consumer Electronics': 'XLK',
    'Communication Equipment': 'SIXG', 'Internet Content & Information': 'SOCL',
    'Internet Retail': 'IBUY', 'Electronic Gaming & Multimedia': 'ESPO',
    # ── HEALTH CARE ──
    'Biotechnology': 'XBI', 'Drug Manufacturers—General': 'XLV',
    'Drug Manufacturers - General': 'XLV',
    'Drug Manufacturers—Specialty & Generic': 'XPH',
    'Drug Manufacturers - Specialty & Generic': 'XPH',
    'Medical Devices': 'IHI', 'Medical Instruments & Supplies': 'IHI',
    'Health Information Services': 'HEAL', 'Medical Care Facilities': 'IHF',
    'Healthcare Plans': 'IHF', 'Diagnostics & Research': 'XBI',
    'Pharmaceutical Retailers': 'XPH', 'Medical Distribution': 'IHF',
    # ── FINANCIALS ──
    'Banks—Diversified': 'KBE', 'Banks - Diversified': 'KBE',
    'Banks—Regional': 'KRE', 'Banks - Regional': 'KRE',
    'Insurance—Diversified': 'KIE', 'Insurance - Diversified': 'KIE',
    'Insurance—Life': 'KIE', 'Insurance - Life': 'KIE',
    'Insurance—Property & Casualty': 'KIE', 'Insurance - Property & Casualty': 'KIE',
    'Insurance Brokers': 'KIE', 'Capital Markets': 'IAI',
    'Financial Data & Stock Exchanges': 'IAI', 'Asset Management': 'IAI',
    'Credit Services': 'IPAY', 'Financial Conglomerates': 'XLF',
    'Mortgage Finance': 'REM',
    'REIT—Diversified': 'VNQ', 'REIT - Diversified': 'VNQ',
    'REIT—Residential': 'VNQ', 'REIT—Industrial': 'VNQ',
    'REIT—Retail': 'VNQ', 'REIT—Office': 'VNQ',
    'REIT—Healthcare Facilities': 'VNQ', 'REIT—Hotel & Motel': 'VNQ',
    'REIT—Specialty': 'VNQ', 'REIT—Mortgage': 'REM',
    'Real Estate Services': 'VNQ', 'Real Estate—Development': 'VNQ',
    # ── ENERGY ──
    'Oil & Gas E&P': 'XOP', 'Oil & Gas Exploration & Production': 'XOP',
    'Oil & Gas Integrated': 'XLE', 'Oil & Gas Midstream': 'AMLP',
    'Oil & Gas Refining & Marketing': 'CRAK',
    'Oil & Gas Equipment & Services': 'OIH', 'Oil & Gas Drilling': 'OIH',
    'Uranium': 'URA', 'Thermal Coal': 'XLE',
    # ── INDUSTRIALS ──
    'Aerospace & Defense': 'XAR', 'Airlines': 'JETS',
    'Railroads': 'IYT', 'Trucking': 'IYT', 'Marine Shipping': 'SEA',
    'Air Freight & Logistics': 'IYT', 'Integrated Freight & Logistics': 'IYT',
    'Farm & Heavy Construction Machinery': 'PAVE',
    'Specialty Industrial Machinery': 'PAVE',
    'Industrial Distribution': 'XLI', 'Engineering & Construction': 'PAVE',
    'Infrastructure Operations': 'IFRA', 'Metal Fabrication': 'XLI',
    'Tools & Accessories': 'XLI', 'Electrical Equipment & Parts': 'XLI',
    'Building Products & Equipment': 'PKB',
    'Pollution & Treatment Controls': 'EVX', 'Waste Management': 'EVX',
    'Conglomerates': 'XLI', 'Rental & Leasing Services': 'XLI',
    'Security & Protection Services': 'XLI',
    'Staffing & Employment Services': 'XLI', 'Consulting Services': 'XLI',
    # ── MATERIALS ──
    'Gold': 'GDX', 'Silver': 'SIL', 'Copper': 'COPX',
    'Steel': 'SLX', 'Aluminum': 'XME',
    'Other Industrial Metals & Mining': 'XME',
    'Other Precious Metals & Mining': 'GDX',
    'Specialty Chemicals': 'XLB', 'Agricultural Inputs': 'MOO',
    'Chemicals': 'XLB', 'Chemicals - Major Diversified': 'XLB',
    'Lumber & Wood Production': 'WOOD', 'Paper & Paper Products': 'XLB',
    'Coking Coal': 'XME', 'Building Materials': 'PKB',
    # ── CONSUMER DISCRETIONARY ──
    'Auto Manufacturers': 'CARZ', 'Auto & Truck Dealerships': 'XLY',
    'Auto Parts': 'CARZ', 'Recreational Vehicles': 'XLY',
    'Residential Construction': 'XHB', 'Home Improvement Retail': 'XHB',
    'Home Furnishings & Fixtures': 'XHB', 'Home Furnishing Retail': 'XHB',
    'Furnishings, Fixtures & Appliances': 'XHB',
    'Restaurants': 'PEJ', 'Resorts & Casinos': 'BJK', 'Gambling': 'BETZ',
    'Leisure': 'PEJ', 'Lodging': 'PEJ',
    'Apparel Retail': 'XRT', 'Apparel Manufacturing': 'XLY',
    'Department Stores': 'XRT', 'Discount Stores': 'XRT',
    'Specialty Retail': 'XRT', 'Luxury Goods': 'XLY',
    'Travel Services': 'AWAY', 'Personal Services': 'XLY',
    # ── CONSUMER STAPLES ──
    'Packaged Foods': 'PBJ', 'Beverages—Non-Alcoholic': 'PBJ',
    'Beverages - Non-Alcoholic': 'PBJ', 'Beverages—Brewers': 'PBJ',
    'Household & Personal Products': 'XLP', 'Tobacco': 'XLP',
    'Food Distribution': 'PBJ', 'Grocery Stores': 'PBJ',
    'Confectioners': 'PBJ', 'Farm Products': 'MOO',
    'Education & Training Services': 'XLP',
    # ── UTILITIES ──
    'Utilities—Regulated Electric': 'RSPU', 'Utilities - Regulated Electric': 'RSPU',
    'Utilities—Regulated Gas': 'RSPU', 'Utilities—Diversified': 'RSPU',
    'Utilities—Independent Power Producers': 'RSPU',
    'Utilities—Regulated Water': 'FIW', 'Utilities—Renewable': 'TAN',
    'Solar Energy': 'TAN',
    # ── COMMUNICATION SERVICES ──
    'Telecom Services': 'XLC', 'Entertainment': 'XLC',
    'Interactive Media & Services': 'SOCL',
    'Publishing': 'XLC', 'Broadcasting': 'XLC',
    'Advertising Agencies': 'XLC',
}

def map_industry_to_etf(industry_name):
    """Map a Yahoo Finance industry name to the closest IBD industry ETF ticker."""
    if not industry_name or industry_name in ('Unknown', '', 'Index', 'ETF', 'IBD-ETF'):
        return None
    # Direct match
    if industry_name in INDUSTRY_TO_ETF:
        return INDUSTRY_TO_ETF[industry_name]
    # Fuzzy keyword fallback
    industry_lower = industry_name.lower()
    for key, etf in INDUSTRY_TO_ETF.items():
        if key.lower() in industry_lower or industry_lower in key.lower():
            return etf
    return None

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

def _clean_yf_df(df):
    """Aggressively coerces OHLCV to numeric, flattening MultiIndex columns and resolving duplicate columns."""
    if df is None or df.empty:
        return df
    
    df = df.copy()
    
    # Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        level_0 = df.columns.get_level_values(0)
        level_1 = df.columns.get_level_values(1) if df.columns.nlevels > 1 else []
        if 'Close' in level_0:
            df.columns = level_0
        elif 'Close' in level_1:
            df.columns = level_1
        else:
            df.columns = level_0
            
    # Remove duplicate columns if any (taking the first occurrence)
    df = df.loc[:, ~df.columns.duplicated()]

    cols_to_clean = ['Open', 'High', 'Low', 'Close', 'Volume']
    for c in cols_to_clean:
        if c in df.columns:
            val = df[c]
            try:
                df[c] = pd.to_numeric(val, errors='coerce')
            except TypeError:
                # Fallback if yfinance bug returned a dict which pd.to_numeric chokes on
                df[c] = pd.to_numeric(val.astype(str), errors='coerce')
            
    if 'Close' in df.columns:
        return df.dropna(subset=['Close'])
    return df

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
        res = {'1M': np.nan, '3M': np.nan, '6M': np.nan, '1Y': np.nan}
        def get_perf(df, days):
            if len(df) < days: return np.nan
            c = df['Close']
            if isinstance(c, pd.DataFrame):
                c = c.iloc[:, 0]
            return float(c.iloc[-1]) / float(c.iloc[-days])

        for key, days in [('1M', 21), ('3M', 63), ('6M', 126), ('1Y', 252)]:
            stock_perf = get_perf(stock_df, days)
            spy_perf = get_perf(spy_df, days)
            if pd.notna(stock_perf) and pd.notna(spy_perf) and spy_perf != 0:
                res[key] = stock_perf / spy_perf
        return res
    except Exception as e:
        if not _rs_error_logged:
            print(f"WARNING: calculate_rs_rating failed: {type(e).__name__}: {e}", flush=True)
            _rs_error_logged = True
        return {'1M': np.nan, '3M': np.nan, '6M': np.nan, '1Y': np.nan}

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

    # Exponential Moving Averages (Oliver Kell uses EMAs, not SMAs)
    df['EMA_10'] = df['Close'].ewm(span=10, adjust=False).mean()
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()

    # ── 8 EMA Structure (High / Close / Low) for Leveraged ETF Screener ──
    df['EMA_8_High']  = df['High'].ewm(span=8, adjust=False).mean()
    df['EMA_8_Close'] = df['Close'].ewm(span=8, adjust=False).mean()
    df['EMA_8_Low']   = df['Low'].ewm(span=8, adjust=False).mean()

    # ── 21 EMA Structure (High / Low) — EMA_21 of Close already computed above ──
    df['EMA_21_High'] = df['High'].ewm(span=21, adjust=False).mean()
    df['EMA_21_Low']  = df['Low'].ewm(span=21, adjust=False).mean()
    
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

    # Double Inside Day (two consecutive inside bars — extreme volatility contraction)
    df['Double_Inside_Day'] = df['Inside_Bar'] & df['Inside_Bar'].shift(1)

    # 3-day SMA and its slope (for pullback velocity measurement)
    df['SMA_3'] = df['Close'].rolling(window=3).mean()
    df['SMA_3_Slope'] = (df['SMA_3'] / df['SMA_3'].shift(3)) - 1.0  # 3-day change in 3SMA

    # 20-day average dollar volume (institutional liquidity filter)
    df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
    df['Avg_Dollar_Vol_20'] = df['Close'] * df['Volume_SMA_20']

    # Upside Reversal — 3 signal types (any qualifies)
    # Signal A: Classic Bullish Reversal Bar
    #   Low probes below previous low, but closes above previous close, in upper 60% of range
    day_range = df['High'] - df['Low']
    close_in_upper_range = (df['Close'] - df['Low']) >= (0.6 * day_range)
    signal_a = (
        (df['Low'] < df['Low'].shift(1)) &
        (df['Close'] > df['Close'].shift(1)) &
        close_in_upper_range
    )

    # Signal B: Hammer / Pin Bar
    #   Lower wick >= 2x upper wick, meaningful range, green candle
    lower_wick = df['Close'] - df['Low']
    upper_wick = df['High'] - df['Close']
    signal_b = (
        (lower_wick >= 2 * upper_wick.replace(0, 0.001)) &
        (day_range > df['ADR_20'].shift(1) * df['Close'].shift(1) / 100 * 0.5) &
        (df['Close'] > df['Open'])
    )

    # Signal C: Volume Reversal
    #   Green candle, 30%+ above avg volume, made new short-term low, closed in upper half
    signal_c = (
        (df['Close'] > df['Open']) &
        (df['Volume'] > df['Volume_SMA_20'] * 1.3) &
        (df['Low'] < df['Low'].shift(1)) &
        (df['Close'] > (df['High'] + df['Low']) / 2)
    )

    df['Upside_Reversal'] = signal_a | signal_b | signal_c

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

    # ── Kell-Zanger Range Breakout Indicators ──────────────────────────────

    # ATR (Average True Range) — 10-day for tightness measurement
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - df['Close'].shift(1)).abs(),
        (df['Low'] - df['Close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    df['ATR_10'] = tr.rolling(window=10).mean()
    df['ATR_14'] = tr.rolling(window=14).mean()  # Standard 14-period ATR for EMA structure screener

    # Bollinger Band Width (20-day, 2 std dev) — narrower = tighter
    bb_std = df['Close'].rolling(window=20).std()
    bb_upper = df['SMA_20'] + 2 * bb_std
    bb_lower = df['SMA_20'] - 2 * bb_std
    df['BB_Width'] = (bb_upper - bb_lower) / df['SMA_20'].replace(0, np.nan)

    # Range Tightness Score (0-100) — Oliver Kell's "tight range" quantified
    # Component 1 (30%): 4-day close range — smaller is tighter
    close_4d_max = df['Close'].rolling(4).max()
    close_4d_min = df['Close'].rolling(4).min()
    close_range_pct = (close_4d_max - close_4d_min) / close_4d_min.replace(0, np.nan)
    # Score: 0-2% range → 100, 10%+ → 0. Linear scale.
    comp1 = ((0.10 - close_range_pct.clip(0, 0.10)) / 0.10) * 100

    # Component 2 (25%): ATR contraction — current ATR vs ATR 20 bars ago
    atr_20_ago = df['ATR_10'].shift(20)
    atr_ratio = df['ATR_10'] / atr_20_ago.replace(0, np.nan)
    # Score: ratio 0.3 → 100, ratio 1.5+ → 0
    comp2 = ((1.5 - atr_ratio.clip(0.3, 1.5)) / 1.2) * 100

    # Component 3 (20%): Volume dry-up — lower RVOL = more dried up
    rvol_clamped = df['RVOL'].clip(0, 3.0)
    comp3 = ((3.0 - rvol_clamped) / 3.0) * 100

    # Component 4 (15%): Bollinger Band Width — narrower = tighter
    bb_clamped = df['BB_Width'].clip(0, 0.20)
    comp4 = ((0.20 - bb_clamped) / 0.20) * 100

    # Component 5 (10%): Body-to-range ratio — small bodies = indecision/accumulation
    body = (df['Close'] - df['Open']).abs()
    body_ratio = body / day_range.replace(0, np.nan)
    # Small body (< 30% of range) scores 100; large body (100%) scores 0
    comp5 = ((1.0 - body_ratio.clip(0, 1.0)) * 100)

    df['Range_Tightness_Score'] = (
        comp1 * 0.30 +
        comp2 * 0.25 +
        comp3 * 0.20 +
        comp4 * 0.15 +
        comp5 * 0.10
    ).round(1)

    # Bull Flag Detection (Dan Zanger pattern)
    # Pole: 15%+ gain in the 20 days ending 5 days ago
    # Flag: 5-day consolidation with range < 8%
    pole_start_close = df['Close'].shift(25)
    pole_end_close = df['Close'].shift(5)
    pole_gain = (pole_end_close - pole_start_close) / pole_start_close.replace(0, np.nan)
    flag_high = df['High'].rolling(5).max()
    flag_low = df['Low'].rolling(5).min()
    flag_range = (flag_high - flag_low) / flag_low.replace(0, np.nan)
    df['Bull_Flag'] = (pole_gain >= 0.15) & (flag_range < 0.08) & (df['Close'] > df['EMA_20'])

    # EMA Crossback Detection (Oliver Kell)
    # Price pulled back to within 1.5% of EMA_10 or EMA_20 from above, then is reclaiming
    near_ema10 = (df['Close'] >= df['EMA_10'] * 0.985) & (df['Close'] <= df['EMA_10'] * 1.015)
    near_ema20 = (df['Close'] >= df['EMA_20'] * 0.985) & (df['Close'] <= df['EMA_20'] * 1.015)
    was_above_ema = (df['Close'].shift(5) > df['EMA_10'].shift(5) * 1.02)  # Was extended above EMAs 5 days ago
    price_reclaiming = df['Close'] >= df['EMA_10']  # Currently at or above EMA
    df['EMA_Crossback'] = (near_ema10 | near_ema20) & was_above_ema & price_reclaiming

    # Consolidation High/Low for last 5 bars (for trigger & stoploss calculation)
    df['Consolidation_High_5'] = df['High'].rolling(5).max()
    df['Consolidation_Low_5'] = df['Low'].rolling(5).min()

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
    
    # Store data directly in memory to pass to portfolio engine
    sim_data_dict = {}
    ibd_rs_dict = {}
    
    if market == 'US':
        # Inject core US Index Proxies for Trade Portal
        us_proxies = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLY', 'XLV', 'XLE', 'XLI', 'XLC', 'XLU', 'XLP', 'XLRE', 'XLB']
        for p in us_proxies:
            tickers.append(p)
            ticker_meta[p] = {'sector': 'Index', 'industry': 'Index', 'market_cap': None}
            
        # Inject IBD tracking ETFs so they are guaranteed to be downloaded
        try:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ibd_etf_config.json')
            with open(config_path, 'r') as f:
                ibd_config = _json.load(f)
            for s in ibd_config.get('sector_etfs', []):
                t = s['ticker']
                if t not in ticker_meta:
                    tickers.append(t)
                    ticker_meta[t] = {'sector': s['gics_sector'], 'industry': 'ETF', 'market_cap': None}
            for e in ibd_config.get('industry_etfs', []):
                t = e['ticker']
                if t not in ticker_meta:
                    tickers.append(t)
                    ticker_meta[t] = {'sector': e.get('sector', 'ETF'), 'industry': 'ETF', 'market_cap': None}
            print(f"Pre-loaded {len(ibd_config.get('sector_etfs', [])) + len(ibd_config.get('industry_etfs', []))} IBD tracking ETFs.", flush=True)
        except Exception as e:
            print(f"Failed to pre-load IBD ETFs into ingestion list: {e}")
        
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
                    # Pre-filter: only keep stocks with last sale >= $2.00
                    # (scanners apply their own Close >= 5 baseline; this just widens the universe
                    #  to capture legitimate stocks like CVGI that temporarily dip below $5)
                    price_str = str(row['lastsale']).replace('$', '').replace(',', '').strip()
                    if price_str and float(price_str) >= 2.0:
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
    chunk_size = 30
    OHLCV_RETENTION_DAYS = 252  # ~1 year of trading days (charts only; portfolio sim is disabled)
    
    benchmark_ticker = 'SPY' if market == 'US' else '^NSEI'
    print(f"Downloading benchmark ({benchmark_ticker}) for RS calculation...", flush=True)
    benchmark_data = yf.download(benchmark_ticker, period=HISTORY_PERIOD, progress=False)
    benchmark_data = _clean_yf_df(benchmark_data)
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:min(i + chunk_size, len(tickers))]
        print(f"Processing chunk {i//chunk_size + 1}/{(len(tickers)//chunk_size)+1}...", flush=True)
        
        max_retries = 3
        retry_delay = 5
        data = None
        
        for attempt in range(max_retries):
            try:
                # Use threads=True with yfinance==1.2.0 (pinned) to avoid dict parsing bug, 
                # while small chunk_size prevents rate-limiting
                time.sleep(1.5)
                temp_data = yf.download(chunk, period=HISTORY_PERIOD, group_by='ticker', progress=False, threads=True)
                
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
                df = data.copy()
            else:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        if ticker in data.columns.get_level_values(0):
                            df = data[ticker].copy()
                        elif ticker in data.columns.get_level_values(1):
                            df = data.xs(ticker, level=1, axis=1).copy()
                        else:
                            skipped_count += 1
                            continue
                    else:
                        df = data[ticker].copy()
                except (KeyError, ValueError, AttributeError):
                    skipped_count += 1
                    continue
            
            df = _clean_yf_df(df)
            
            if df is None or df.empty or len(df) < 5:
                skipped_count += 1
                continue
            
            last = calculate_indicators(df)
            if last is not None:
                success_count += 1
                rs_raws = calculate_rs_rating(df, benchmark_data)
                rs_raw_1m = None if pd.isna(rs_raws['1M']) else float(rs_raws['1M'])
                rs_raw_3m = None if pd.isna(rs_raws['3M']) else float(rs_raws['3M'])
                rs_raw_6m = None if pd.isna(rs_raws['6M']) else float(rs_raws['6M'])
                rs_raw_1y = None if pd.isna(rs_raws['1Y']) else float(rs_raws['1Y'])
                
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
                        rs_raw_1y,
                        rs_raw_1m,
                        rs_raw_3m,
                        rs_raw_6m,
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
                        0.0, # RS_Rating_1M
                        0.0, # RS_Rating_3M
                        0.0, # RS_Rating_6M
                        ticker_meta.get(ticker, {}).get('sector', 'Unknown'),
                        ticker_meta.get(ticker, {}).get('industry', 'Unknown'),
                        _parse_market_cap(ticker_meta.get(ticker, {}).get('market_cap')),
                        int(last['Stage']) if pd.notna(last['Stage']) else None,
                        _nan_to_none(last['Avg_Dollar_Vol_20']),
                        _nan_to_none(last['SMA_3_Slope']),
                        _safe_bool(last['Upside_Reversal']),
                        _safe_bool(last['Double_Inside_Day']),
                        map_industry_to_etf(ticker_meta.get(ticker, {}).get('industry', 'Unknown')),
                        # Kell-Zanger Range Breakout columns
                        _nan_to_none(last['EMA_10']),
                        _nan_to_none(last['EMA_20']),
                        _nan_to_none(last['EMA_21']),
                        _nan_to_none(last['Range_Tightness_Score']),
                        _safe_bool(last['Bull_Flag']),
                        _safe_bool(last['EMA_Crossback']),
                        _nan_to_none(last['Consolidation_High_5']),
                        _nan_to_none(last['Consolidation_Low_5']),
                        # EMA Structure columns (8 EMA & 21 EMA screener)
                        _nan_to_none(last['EMA_8_High']),
                        _nan_to_none(last['EMA_8_Close']),
                        _nan_to_none(last['EMA_8_Low']),
                        _nan_to_none(last['EMA_21_High']),
                        _nan_to_none(last['EMA_21_Low']),
                        _nan_to_none(last['ATR_14']),
                    )
                    all_data.append(record)
                    
                    # Build sim DataFrame (full history for portfolio engine)
                    df_sim = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                    df_sim.index.name = 'Date'
                    df_sim = df_sim.reset_index()
                    df_sim['Date'] = pd.to_datetime(df_sim['Date'])
                    df_sim['Ticker'] = ticker
                    sim_data_dict[ticker] = df_sim
                    
                    # Vectorized OHLCV tuple creation (replaces slow iterrows loop)
                    # Trim to last OHLCV_RETENTION_DAYS for DB persistence only (US only to save space)
                    if market == 'US':
                        ohlcv_df = df[['Open', 'High', 'Low', 'Close', 'Volume']].tail(OHLCV_RETENTION_DAYS).copy()
                        ohlcv_df.index.name = 'Date'
                        ohlcv_df = ohlcv_df.reset_index()
                        ohlcv_df['Date'] = ohlcv_df['Date'].dt.strftime('%Y-%m-%d')
                        ohlcv_df.insert(0, 'Ticker', ticker)
                        # Convert NaN to None and build tuples in bulk
                        ohlcv_df = ohlcv_df.where(pd.notnull(ohlcv_df), None)
                        all_ohlcv.extend(list(ohlcv_df.itertuples(index=False, name=None)))
                        
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
    if market == 'US':
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
            # ── IBD Industry & Theme ETFs (from ETF Industry Tracking spreadsheet) ──
            # Energy sub-industries
            'XOP', 'CRAK', 'OIH', 'AMLP', 'FCG', 'URA', 'NLR', 'NUKZ',
            # Materials sub-industries
            'GDX', 'SIL', 'COPX', 'SLX', 'XME', 'REMX', 'MOO', 'DBA', 'WOOD', 'LIT',
            # Industrials sub-industries
            'XAR', 'ITA', 'JETS', 'IYT', 'XTN', 'PAVE', 'IFRA', 'HVAC', 'ROBO', 'BOTZ', 'ARKQ', 'PRNT', 'SEA',
            # Consumer Discretionary sub-industries
            'XHB', 'PKB', 'CARZ', 'DRIV', 'RTH', 'IBUY', 'XRT', 'PEJ', 'EATZ', 'BJK', 'BETZ', 'AWAY', 'ESPO', 'PAWZ', 'MADE',
            # Consumer Staples sub-industries
            'PBJ', 'MSOS',
            # Health Care sub-industries
            'XBI', 'XPH', 'XHE', 'IHI', 'IHF', 'GNOM', 'HEAL', 'OZEM', 'ARKG',
            # Financials sub-industries
            'KBE', 'KRE', 'KIE', 'IAI', 'IPAY', 'FINX', 'BIZD', 'VNQ', 'REM', 'DTCR',
            # Utilities sub-industries
            'RSPU', 'FIW', 'TAN', 'FAN', 'CTEC', 'BATT', 'POWR', 'HYDR', 'EVX',
            # Technology sub-industries
            'SMH', 'XSD', 'IGV', 'WCLD', 'AIQ', 'SIXG', 'QTUM', 'BLOK', 'SOCL',
            # Crypto
            'BITQ', 'BKCH', 'WGMI',
            # International
            'EWW', 'INDA', 'VGK', 'EUFN', 'KWEB', 'CQQQ', 'AFK', 'EWT', 'EWY', 'EUAD', 'ASEA', 'KSA', 'EWA',
            # Thematic
            'IPO', 'ARKX', 'SHLD',
            # ── Leveraged ETF Underlying ETFs (expanded) ──
            'SPHB', 'PPH', 'FDN', 'GDXJ', 'FNGS', 'MAGS', 'ARKK',
            'URNM', 'VIXY', 'WEAT', 'CORN', 'ROBT', 'ASHR',
        ]

        # Build lev ETF ticker list separately (downloaded with shorter history)
        lev_etf_tickers_only = []
        try:
            from api.routers.lev_etf import LEV_ETF_LIST
            lev_etf_tickers_only = [e['ticker'] for e in LEV_ETF_LIST]
            print(f"Loaded {len(lev_etf_tickers_only)} leveraged ETF tickers for EMA structure screener.", flush=True)
        except Exception as lev_err:
            print(f"Warning: Could not load lev ETF tickers: {lev_err}", flush=True)
    else:
        # India: no sector ETF OHLCV needed (saves DB space)
        sector_etf_tickers = []
        lev_etf_tickers_only = []
    
    # Filter out any ETFs that happen to already be in the universe
    existing_tickers = set(r[0] for r in all_ohlcv)  # ticker is first element of tuple
    etfs_to_download = [t for t in sector_etf_tickers if t not in existing_tickers]
    
    # ── Download Sector/Underlying ETFs (with full HISTORY_PERIOD for charts) ──
    if etfs_to_download:
        print(f"Downloading OHLCV for {len(etfs_to_download)} sector ETFs (period={HISTORY_PERIOD})...", flush=True)
        try:
            # Use threads=True to avoid yfinance dictionary parsing bug
            etf_data = yf.download(etfs_to_download, period=HISTORY_PERIOD, group_by='ticker', threads=True)
            
            for etf_ticker in etfs_to_download:
                try:
                    if len(etfs_to_download) > 1:
                        df_etf = etf_data[etf_ticker].dropna(subset=['Close'])
                    else:
                        df_etf = etf_data.dropna(subset=['Close'])
                    
                    df_etf = _clean_yf_df(df_etf)
                    
                    # Build sim DataFrame (full history for portfolio engine)
                    df_sim = df_etf[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                    df_sim.index.name = 'Date'
                    df_sim = df_sim.reset_index()
                    df_sim['Date'] = pd.to_datetime(df_sim['Date'])
                    df_sim['Ticker'] = etf_ticker
                    sim_data_dict[etf_ticker] = df_sim
                    
                    # Vectorized OHLCV tuple creation (trimmed for DB)
                    ohlcv_df = df_etf[['Open', 'High', 'Low', 'Close', 'Volume']].tail(OHLCV_RETENTION_DAYS).copy()
                    ohlcv_df.index.name = 'Date'
                    ohlcv_df = ohlcv_df.reset_index()
                    ohlcv_df['Date'] = ohlcv_df['Date'].dt.strftime('%Y-%m-%d')
                    ohlcv_df.insert(0, 'Ticker', etf_ticker)
                    ohlcv_df = ohlcv_df.where(pd.notnull(ohlcv_df), None)
                    etf_count = len(ohlcv_df)
                    all_ohlcv.extend(list(ohlcv_df.itertuples(index=False, name=None)))
                    
                    # ALSO compute indicators and add to screen_data (needed for Lev ETF scanner)
                    if len(df_etf) >= 5:
                        last_etf = calculate_indicators(df_etf)
                        if last_etf is not None:
                            rs_raw_etf = calculate_rs_rating(df_etf, benchmark_data)
                            rs_raw_clean_etf = None if (rs_raw_etf is None or pd.isna(rs_raw_etf.get('1Y'))) else float(rs_raw_etf['1Y'])
                            
                            etf_record = (
                                etf_ticker,
                                market,
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
                                None,  # RS_Raw_1M
                                None,  # RS_Raw_3M
                                None,  # RS_Raw_6M
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
                                0.0, # RS_Rating_1M
                                0.0, # RS_Rating_3M
                                0.0, # RS_Rating_6M
                                'ETF', # Sector
                                'ETF', # Industry
                                0.0, # Market Cap
                                int(last_etf['Stage']) if pd.notna(last_etf['Stage']) else None,
                                _nan_to_none(last_etf['Avg_Dollar_Vol_20']),
                                _nan_to_none(last_etf['SMA_3_Slope']),
                                _safe_bool(last_etf['Upside_Reversal']),
                                _safe_bool(last_etf['Double_Inside_Day']),
                                etf_ticker,  # IBD_ETF_Proxy — ETF is its own proxy
                                # Kell-Zanger Range Breakout columns
                                _nan_to_none(last_etf['EMA_10']),
                                _nan_to_none(last_etf['EMA_20']),
                                _nan_to_none(last_etf['EMA_21']),
                                _nan_to_none(last_etf['Range_Tightness_Score']),
                                _safe_bool(last_etf['Bull_Flag']),
                                _safe_bool(last_etf['EMA_Crossback']),
                                _nan_to_none(last_etf['Consolidation_High_5']),
                                _nan_to_none(last_etf['Consolidation_Low_5']),
                                # EMA Structure columns (8 EMA & 21 EMA screener)
                                _nan_to_none(last_etf['EMA_8_High']),
                                _nan_to_none(last_etf['EMA_8_Close']),
                                _nan_to_none(last_etf['EMA_8_Low']),
                                _nan_to_none(last_etf['EMA_21_High']),
                                _nan_to_none(last_etf['EMA_21_Low']),
                                _nan_to_none(last_etf['ATR_14']),
                            )
                            all_data.append(etf_record)
                            
                    print(f"  {etf_ticker}: {etf_count} days + indicators", flush=True)
                except Exception as etf_err:
                    print(f"  Warning: Failed to get OHLCV for {etf_ticker}: {etf_err}", flush=True)
        except Exception as etf_batch_err:
            print(f"  Warning: Sector ETF batch download failed: {etf_batch_err}", flush=True)

    # ── Download Leveraged ETFs (with shorter 1y period — only need indicators) ──
    # Lev ETFs only need screen_data for the EMA structure screener.
    # Skip sim_data_dict (no portfolio sim) and use '1y' to save download time.
    lev_to_download = [t for t in lev_etf_tickers_only if t not in existing_tickers and t not in set(etfs_to_download)]
    
    if lev_to_download:
        LEV_DOWNLOAD_PERIOD = '1y'  # 1 year is enough for EMA(21) + ATR(14) + 200 SMA
        # Download in chunks to avoid yfinance rate limits
        lev_chunk_size = 100
        print(f"Downloading {len(lev_to_download)} leveraged ETFs (period={LEV_DOWNLOAD_PERIOD}, chunks of {lev_chunk_size})...", flush=True)
        
        for lev_i in range(0, len(lev_to_download), lev_chunk_size):
            lev_chunk = lev_to_download[lev_i:lev_i + lev_chunk_size]
            try:
                time.sleep(2)  # Brief pause between chunks
                # Use threads=True to avoid yfinance dictionary parsing bug
                lev_data = yf.download(lev_chunk, period=LEV_DOWNLOAD_PERIOD, group_by='ticker', threads=True)
                
                if lev_data is None or lev_data.empty:
                    print(f"  Lev chunk {lev_i//lev_chunk_size + 1}: empty data, skipping", flush=True)
                    continue
                
                lev_success = 0
                for lev_ticker in lev_chunk:
                    try:
                        if isinstance(lev_data.columns, pd.MultiIndex):
                            if lev_ticker in lev_data.columns.get_level_values(0):
                                df_lev = lev_data[lev_ticker].copy()
                            elif lev_ticker in lev_data.columns.get_level_values(1):
                                df_lev = lev_data.xs(lev_ticker, level=1, axis=1).copy()
                            else:
                                continue
                        else:
                            # If flat dataframe but no multiindex, it could be a single ticker return
                            if len(lev_chunk) == 1:
                                df_lev = lev_data.copy()
                            else:
                                df_lev = lev_data[lev_ticker].copy()
                            
                        df_lev = _clean_yf_df(df_lev)
                        
                        if df_lev is None or df_lev.empty or len(df_lev) < 5:
                            continue
                        
                        # Store OHLCV for chart rendering
                        ohlcv_df = df_lev[['Open', 'High', 'Low', 'Close', 'Volume']].tail(OHLCV_RETENTION_DAYS).copy()
                        ohlcv_df.index.name = 'Date'
                        ohlcv_df = ohlcv_df.reset_index()
                        ohlcv_df['Date'] = ohlcv_df['Date'].dt.strftime('%Y-%m-%d')
                        ohlcv_df.insert(0, 'Ticker', lev_ticker)
                        ohlcv_df = ohlcv_df.where(pd.notnull(ohlcv_df), None)
                        all_ohlcv.extend(list(ohlcv_df.itertuples(index=False, name=None)))
                        
                        # Compute indicators for screen_data (EMA structure screener)
                        last_lev = calculate_indicators(df_lev)
                        if last_lev is not None:
                            rs_raw_lev = calculate_rs_rating(df_lev, benchmark_data)
                            rs_raw_clean_lev = None if (rs_raw_lev is None or pd.isna(rs_raw_lev.get('1Y'))) else float(rs_raw_lev['1Y'])
                            
                            lev_record = (
                                lev_ticker,
                                market,
                                str(last_lev.name),
                                _nan_to_none(last_lev['Close']),
                                _nan_to_none(last_lev['Volume']),
                                _nan_to_none(last_lev['SMA_5']),
                                _nan_to_none(last_lev['SMA_9']),
                                _nan_to_none(last_lev['SMA_10']),
                                _nan_to_none(last_lev['SMA_20']),
                                _nan_to_none(last_lev['SMA_21']),
                                _nan_to_none(last_lev['SMA_50']),
                                _nan_to_none(last_lev['SMA_100']),
                                _nan_to_none(last_lev['SMA_200']),
                                _nan_to_none(last_lev['RVOL']),
                                _nan_to_none(last_lev['ADR_20']),
                                _nan_to_none(last_lev['Pct_From_52W_High']),
                                _safe_bool(last_lev['In_Stage_2']),
                                _safe_bool(last_lev['Tight_Setup']),
                                _safe_bool(last_lev['Near_Horizontal_Resistance']),
                                rs_raw_clean_lev,
                                None,  # RS_Raw_1M
                                None,  # RS_Raw_3M
                                None,  # RS_Raw_6M
                                _safe_bool(last_lev['Inside_Bar']),
                                _safe_bool(last_lev['Golden_Crossover']),
                                _safe_bool(last_lev['Gap_Up']),
                                _safe_bool(last_lev['Gap_Down']),
                                _safe_bool(last_lev['VCP_Approximation']),
                                _nan_to_none(last_lev['Momentum_1D']),
                                _nan_to_none(last_lev['Momentum_1W']),
                                _nan_to_none(last_lev['Momentum_1M']),
                                _nan_to_none(last_lev['Momentum_3M']),
                                _nan_to_none(last_lev['Momentum_6M']),
                                _nan_to_none(last_lev['Momentum_1Y']),
                                0.0, # Placeholder for RS_Rating
                                0.0, # RS_Rating_1M
                                0.0, # RS_Rating_3M
                                0.0, # RS_Rating_6M
                                'Leveraged ETF', # Sector
                                'Leveraged ETF', # Industry
                                0.0, # Market Cap
                                int(last_lev['Stage']) if pd.notna(last_lev['Stage']) else None,
                                _nan_to_none(last_lev['Avg_Dollar_Vol_20']),
                                _nan_to_none(last_lev['SMA_3_Slope']),
                                _safe_bool(last_lev['Upside_Reversal']),
                                _safe_bool(last_lev['Double_Inside_Day']),
                                lev_ticker,  # IBD_ETF_Proxy — ETF is its own proxy
                                # Kell-Zanger Range Breakout columns
                                _nan_to_none(last_lev['EMA_10']),
                                _nan_to_none(last_lev['EMA_20']),
                                _nan_to_none(last_lev['EMA_21']),
                                _nan_to_none(last_lev['Range_Tightness_Score']),
                                _safe_bool(last_lev['Bull_Flag']),
                                _safe_bool(last_lev['EMA_Crossback']),
                                _nan_to_none(last_lev['Consolidation_High_5']),
                                _nan_to_none(last_lev['Consolidation_Low_5']),
                                # EMA Structure columns (8 EMA & 21 EMA screener)
                                _nan_to_none(last_lev['EMA_8_High']),
                                _nan_to_none(last_lev['EMA_8_Close']),
                                _nan_to_none(last_lev['EMA_8_Low']),
                                _nan_to_none(last_lev['EMA_21_High']),
                                _nan_to_none(last_lev['EMA_21_Low']),
                                _nan_to_none(last_lev['ATR_14']),
                            )
                            all_data.append(lev_record)
                            lev_success += 1
                    except Exception as lev_err:
                        if lev_success == 0:  # Log first failure per chunk for debugging
                            print(f"  Warning: {lev_ticker} processing failed: {lev_err}", flush=True)
                
                print(f"  Lev chunk {lev_i//lev_chunk_size + 1}/{(len(lev_to_download)//lev_chunk_size)+1}: {lev_success}/{len(lev_chunk)} processed", flush=True)
            except Exception as lev_batch_err:
                print(f"  Warning: Lev ETF chunk download failed: {lev_batch_err}", flush=True)
    
    print(f"Total OHLCV records for DB (pre-trimmed to {OHLCV_RETENTION_DAYS} days/ticker): {len(all_ohlcv):,}", flush=True)

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
            Market {sql_types["TEXT"]},
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
            RS_Raw_1M {sql_types["REAL"]},
            RS_Raw_3M {sql_types["REAL"]},
            RS_Raw_6M {sql_types["REAL"]},
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
            RS_Rating_1M {sql_types["REAL"]},
            RS_Rating_3M {sql_types["REAL"]},
            RS_Rating_6M {sql_types["REAL"]},
            Sector {sql_types["TEXT"]},
            Industry {sql_types["TEXT"]},
            Market_Cap {sql_types["REAL"]},
            Stage {sql_types["INTEGER"]},
            Avg_Dollar_Vol_20 {sql_types["REAL"]},
            SMA_3_Slope {sql_types["REAL"]},
            Upside_Reversal {sql_types["BOOLEAN"]},
            Double_Inside_Day {sql_types["BOOLEAN"]},
            IBD_ETF_Proxy {sql_types["TEXT"]},
            EMA_10 {sql_types["REAL"]},
            EMA_20 {sql_types["REAL"]},
            EMA_21 {sql_types["REAL"]},
            Range_Tightness_Score {sql_types["REAL"]},
            Bull_Flag {sql_types["BOOLEAN"]},
            EMA_Crossback {sql_types["BOOLEAN"]},
            Consolidation_High_5 {sql_types["REAL"]},
            Consolidation_Low_5 {sql_types["REAL"]},
            EMA_8_High {sql_types["REAL"]},
            EMA_8_Close {sql_types["REAL"]},
            EMA_8_Low {sql_types["REAL"]},
            EMA_21_High {sql_types["REAL"]},
            EMA_21_Low {sql_types["REAL"]},
            ATR_14 {sql_types["REAL"]}
        )
    ''')
    
    # Defensive schema migration for PostgreSQL to append missing RS multi-timeframes dynamically
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        try:
            cursor.execute("SELECT RS_Rating_1M FROM screen_data LIMIT 1")
        except Exception:
            conn.rollback()
            print("Migrating screen_data to include multi-timeframe RS columns...", flush=True)
            for new_col in ["RS_Rating_1M", "RS_Rating_3M", "RS_Rating_6M", "RS_Raw_1M", "RS_Raw_3M", "RS_Raw_6M"]:
                try:
                    cursor.execute(f"ALTER TABLE screen_data ADD COLUMN {new_col} REAL")
                    conn.commit()
                except Exception:
                    conn.rollback()

    # Defensive schema migration: Power Pullback columns
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        for new_col, col_type in [("Avg_Dollar_Vol_20", "REAL"), ("SMA_3_Slope", "REAL"), ("Upside_Reversal", "BOOLEAN"), ("Double_Inside_Day", "BOOLEAN")]:
            try:
                cursor.execute(f"SELECT {new_col} FROM screen_data LIMIT 1")
            except Exception:
                conn.rollback()
                try:
                    cursor.execute(f"ALTER TABLE screen_data ADD COLUMN {new_col} {col_type}")
                    conn.commit()
                    print(f"Migrated screen_data: added {new_col} column.", flush=True)
                except Exception:
                    conn.rollback()

    # Defensive schema migration: IBD ETF Proxy column
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        try:
            cursor.execute("SELECT IBD_ETF_Proxy FROM screen_data LIMIT 1")
        except Exception:
            conn.rollback()
            try:
                cursor.execute("ALTER TABLE screen_data ADD COLUMN IBD_ETF_Proxy VARCHAR(255)")
                conn.commit()
                print("Migrated screen_data: added IBD_ETF_Proxy column.", flush=True)
            except Exception:
                conn.rollback()

    # Defensive schema migration: Kell-Zanger Range Breakout columns
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        kz_cols = [
            ("EMA_10", "DOUBLE PRECISION"), ("EMA_20", "DOUBLE PRECISION"), ("EMA_21", "DOUBLE PRECISION"),
            ("Range_Tightness_Score", "DOUBLE PRECISION"),
            ("Bull_Flag", "BOOLEAN"), ("EMA_Crossback", "BOOLEAN"),
            ("Consolidation_High_5", "DOUBLE PRECISION"), ("Consolidation_Low_5", "DOUBLE PRECISION"),
        ]
        for new_col, col_type in kz_cols:
            try:
                cursor.execute(f"SELECT {new_col} FROM screen_data LIMIT 1")
            except Exception:
                conn.rollback()
                try:
                    cursor.execute(f"ALTER TABLE screen_data ADD COLUMN {new_col} {col_type}")
                    conn.commit()
                    print(f"Migrated screen_data: added {new_col} column.", flush=True)
                except Exception:
                    conn.rollback()

    # Defensive schema migration: EMA Structure columns (8 EMA & 21 EMA screener)
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        ema_struct_cols = [
            ("EMA_8_High", "DOUBLE PRECISION"), ("EMA_8_Close", "DOUBLE PRECISION"), ("EMA_8_Low", "DOUBLE PRECISION"),
            ("EMA_21_High", "DOUBLE PRECISION"), ("EMA_21_Low", "DOUBLE PRECISION"),
            ("ATR_14", "DOUBLE PRECISION"),
        ]
        for new_col, col_type in ema_struct_cols:
            try:
                cursor.execute(f"SELECT {new_col} FROM screen_data LIMIT 1")
            except Exception:
                conn.rollback()
                try:
                    cursor.execute(f"ALTER TABLE screen_data ADD COLUMN {new_col} {col_type}")
                    conn.commit()
                    print(f"Migrated screen_data: added {new_col} column.", flush=True)
                except Exception:
                    conn.rollback()
    
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

    # IBD ETF Rotation Ranks table (parallel to industry_ranks, for ETFs only)
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS ibd_etf_ranks (
            Date {sql_types["TEXT"]},
            Market {sql_types["TEXT"]} DEFAULT 'US',
            Tier {sql_types["TEXT"]},
            ETF_Ticker {sql_types["TEXT"]},
            ETF_Name {sql_types["TEXT"]},
            Sector {sql_types["TEXT"]},
            Rank_1D INTEGER,
            Rank_1W INTEGER,
            Rank_1M INTEGER,
            Rank_3M INTEGER,
            Rank_6M INTEGER,
            Rank_1Y INTEGER,
            Momentum_1D {sql_types["REAL"]},
            Momentum_1W {sql_types["REAL"]},
            Momentum_1M {sql_types["REAL"]},
            Momentum_3M {sql_types["REAL"]},
            Momentum_6M {sql_types["REAL"]},
            Momentum_1Y {sql_types["REAL"]},
            Pct_From_52W_High {sql_types["REAL"]},
            Stage INTEGER,
            Above_50DMA {sql_types["BOOLEAN"]},
            Above_200DMA {sql_types["BOOLEAN"]},
            PRIMARY KEY (Date, Market, ETF_Ticker)
        )
    ''')

    if not (DATABASE_URL and DATABASE_URL.startswith("postgres")):
        cursor.execute("PRAGMA synchronous = OFF")
        cursor.execute("PRAGMA journal_mode = MEMORY")

    SCREEN_DATA_COLS = [
        "Ticker", "Market", "Date", "Close", "Volume", "SMA_5", "SMA_9", "SMA_10", "SMA_20", "SMA_21", "SMA_50", "SMA_100", "SMA_200",
        "RVOL", "ADR_20", "Pct_From_52W_High", "In_Stage_2", "Tight_Setup", "Near_Horizontal_Resistance", 
        "RS_Raw", "RS_Raw_1M", "RS_Raw_3M", "RS_Raw_6M", "Inside_Bar", "Golden_Crossover", "Gap_Up", "Gap_Down", "VCP_Approximation", 
        "Momentum_1D", "Momentum_1W", "Momentum_1M", "Momentum_3M", "Momentum_6M", "Momentum_1Y", 
        "RS_Rating", "RS_Rating_1M", "RS_Rating_3M", "RS_Rating_6M",
        "Sector", "Industry", "Market_Cap", "Stage",
        "Avg_Dollar_Vol_20", "SMA_3_Slope", "Upside_Reversal", "Double_Inside_Day",
        "IBD_ETF_Proxy",
        # Kell-Zanger Range Breakout columns
        "EMA_10", "EMA_20", "EMA_21", "Range_Tightness_Score",
        "Bull_Flag", "EMA_Crossback", "Consolidation_High_5", "Consolidation_Low_5",
        # EMA Structure columns (8 EMA & 21 EMA screener)
        "EMA_8_High", "EMA_8_Close", "EMA_8_Low", "EMA_21_High", "EMA_21_Low", "ATR_14",
    ]
    col_str = ", ".join(SCREEN_DATA_COLS)
    placeholders = ", ".join(['%s'] * len(SCREEN_DATA_COLS)) if (DATABASE_URL and DATABASE_URL.startswith("postgres")) else ", ".join(['?'] * len(SCREEN_DATA_COLS))

    # Before inserting, aggressively clean old data to stay within Neon 512 MB limit
    print(f"[{market}] Performing full database cleanup...", flush=True)
    
    is_pg = DATABASE_URL and DATABASE_URL.startswith("postgres")
    
    if is_pg:
        if market == 'US':
            # TRUNCATE daily_ohlcv to IMMEDIATELY reclaim disk space.
            # Postgres DELETE only marks rows as dead tuples — disk space is NOT freed,
            # causing the 512 MB Neon limit to be exceeded on the next INSERT cycle.
            # TRUNCATE resets the table files to zero, reclaiming all space instantly.
            # This is safe because: (a) IN market no longer stores OHLCV, so the table is US-only.
            # (b) We rebuild the full US OHLCV dataset from scratch every run anyway.
            cursor.execute("TRUNCATE TABLE daily_ohlcv")
            conn.commit()
            print(f"[{market}] TRUNCATED daily_ohlcv table (immediate disk space reclaim).", flush=True)
        # IN market: skip daily_ohlcv cleanup entirely (IN no longer writes to this table)
    else:
        # SQLite: simple DELETE is fine (no dead tuple bloat)
        cursor.execute(f"DELETE FROM daily_ohlcv WHERE Market = '{market}'")
    
    # Clear current market's data from remaining tables
    cursor.execute(f"DELETE FROM screen_data WHERE Market = '{market}'")
    cursor.execute(f"DELETE FROM scanner_results WHERE Market = '{market}'")
    cursor.execute(f"DELETE FROM market_breadth_history WHERE Market = '{market}'")
    cursor.execute(f"DELETE FROM ibd_etf_ranks WHERE Market = '{market}'")
    conn.commit()
    
    # On Postgres, run VACUUM on the smaller tables to reclaim dead tuple space
    # (prevents cumulative bloat from daily DELETE+INSERT cycles)
    if is_pg:
        old_autocommit = conn.autocommit
        conn.autocommit = True
        try:
            cursor.execute("VACUUM screen_data")
            cursor.execute("VACUUM scanner_results")
            cursor.execute("VACUUM market_breadth_history")
            cursor.execute("VACUUM ibd_etf_ranks")
            cursor.execute("VACUUM industry_ranks")
            print(f"[{market}] VACUUM complete on auxiliary tables.", flush=True)
        except Exception as vac_err:
            print(f"[{market}] VACUUM warning (non-fatal): {vac_err}", flush=True)
        conn.autocommit = old_autocommit

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
    
    if market == 'US':
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
    else:
        print(f"Skipping daily_ohlcv insertion for {market} market to save project size limit (512MB).", flush=True)
    
    
    print("Calculating multi-timeframe RS Ratings from RS_Raw percentile ranks...", flush=True)
    cursor.execute(f"SELECT Ticker, RS_Raw, RS_Raw_1M, RS_Raw_3M, RS_Raw_6M FROM screen_data WHERE Market = '{market}' AND RS_Raw IS NOT NULL")
    rows = cursor.fetchall()
    df_db = pd.DataFrame(rows, columns=['Ticker', 'RS_Raw', 'RS_Raw_1M', 'RS_Raw_3M', 'RS_Raw_6M'])
    df_db = df_db.dropna(subset=['RS_Raw'])
    
    print(f"Found {len(df_db)} tickers with valid RS_Raw values.", flush=True)
    
    if not df_db.empty:
        df_db['RS_Rating'] = df_db['RS_Raw'].rank(pct=True) * 99
        df_db['RS_Rating_1M'] = df_db['RS_Raw_1M'].rank(pct=True) * 99
        df_db['RS_Rating_3M'] = df_db['RS_Raw_3M'].rank(pct=True) * 99
        df_db['RS_Rating_6M'] = df_db['RS_Raw_6M'].rank(pct=True) * 99
        
        update_data = []
        for _, row in df_db.iterrows():
            r1 = None if pd.isna(row['RS_Rating']) else float(row['RS_Rating'])
            r2 = None if pd.isna(row['RS_Rating_1M']) else float(row['RS_Rating_1M'])
            r3 = None if pd.isna(row['RS_Rating_3M']) else float(row['RS_Rating_3M'])
            r4 = None if pd.isna(row['RS_Rating_6M']) else float(row['RS_Rating_6M'])
            update_data.append((r1, r2, r3, r4, row['Ticker']))
            if r1 is not None:
                ibd_rs_dict[row['Ticker']] = r1
        
        for i in range(0, len(update_data), batch_size):
            batch = update_data[i:i + batch_size]
            print(f"  Updating RS_Rating batch {i//batch_size + 1} for {len(batch)} tickers...", flush=True)
            if DATABASE_URL and DATABASE_URL.startswith("postgres"):
                cursor.executemany("UPDATE screen_data SET RS_Rating = %s, RS_Rating_1M = %s, RS_Rating_3M = %s, RS_Rating_6M = %s WHERE Ticker = %s", batch)
            else:
                cursor.executemany("UPDATE screen_data SET RS_Rating = ?, RS_Rating_1M = ?, RS_Rating_3M = ?, RS_Rating_6M = ? WHERE Ticker = ?", batch)
            conn.commit()
        
        print(f"Successfully updated multi-timeframe RS Ratings for {len(update_data)} tickers.", flush=True)
            
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
        "htf": (
            "In_Stage_2 AND Momentum_3M > 0.90 "
            "AND Pct_From_52W_High BETWEEN -25 AND -2 "
            "AND RVOL < 0.85 AND RS_Rating >= 80 AND ADR_20 >= 4.0"
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
        "long-term-pf":           "f.peg_ratio > 0 AND f.peg_ratio < 1.5 AND f.revenue_doubled IS TRUE AND d.In_Stage_2 IS TRUE AND d.Market_Cap >= 500",
        "modern-breakout":        (
            "In_Stage_2 AND RS_Rating >= 95 AND Pct_From_52W_High > -20 "
            "AND (Tight_Setup OR VCP_Approximation OR Inside_Bar) "
            "AND abs(Close - SMA_20) / SMA_20 <= 0.06"
        ),
        "modern-pullback":        (
            "In_Stage_2 AND RS_Rating >= 90 AND Close >= SMA_50 AND SMA_20 >= SMA_50 "
            "AND RVOL < 1.0 "
            "AND ((abs(Close - SMA_20) / SMA_20 <= 0.02) OR (abs(Close - SMA_10) / SMA_10 <= 0.02)) "
            "AND (Inside_Bar OR Tight_Setup OR VCP_Approximation)"
        ),
        "power-pullback":         (
            f"Avg_Dollar_Vol_20 > {'20000000' if market == 'US' else '50000000'} "
            "AND SMA_3_Slope BETWEEN -0.03 AND -0.005 "
            "AND Close > SMA_50 "
            "AND Close >= SMA_21 * 0.95 "
            "AND RS_Rating_6M >= 80 "
            "AND (Upside_Reversal OR Tight_Setup OR Inside_Bar OR Double_Inside_Day OR VCP_Approximation)"
        ),
        # ⚡ Kell-Zanger Range Breakout — the ultimate tight-range breakout scanner
        # Layer 2A (Kell): Stage 2 + EMA alignment + RS leadership + institutional liquidity
        # Layer 2B (Zanger): Near 52W highs + 3M momentum positive
        # Layer 3: Range Tightness Score >= 60 + at least one constructive pattern
        "kell-zanger":            (
            "In_Stage_2 AND Close >= EMA_10 AND EMA_10 >= EMA_20 "
            "AND Close >= 10 AND Volume >= 300000 "
            "AND RS_Rating >= 80 "
            "AND Pct_From_52W_High > -15 "
            "AND Momentum_3M > 0 "
            "AND Range_Tightness_Score >= 60 "
            "AND (Tight_Setup OR VCP_Approximation OR Inside_Bar OR Bull_Flag OR EMA_Crossback)"
        ),
    }
    
    baseline = "Close >= 5" if market == "US" else "Close > 0"
    
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

    # Power Pullback + Kell-Zanger: apply industry rank top-50% post-filter (requires JOIN to industry_ranks)
    # Get the industry rank cutoff (total industries / 2)
    INDUSTRY_FILTERED_SCANNERS = ['power-pullback', 'kell-zanger']
    if market in ['US', 'IN']:
        latest_date_q = f"SELECT MAX(Date) FROM industry_ranks WHERE Market = '{market}'"
        cursor.execute(f"SELECT COUNT(*) FROM industry_ranks WHERE Category = 'Industry' AND Market = '{market}' AND Date = ({latest_date_q})")
        industry_count_row = cursor.fetchone()
        total_industries = (industry_count_row[0] if industry_count_row else 0)
        top_50_cutoff = max(1, total_industries // 2)
        
        if total_industries > 0:
            # Get industries in top 50% by 1M or 3M rank
            cursor.execute(f"""
                SELECT Name FROM industry_ranks 
                WHERE Category = 'Industry' AND Market = '{market}' AND Date = ({latest_date_q})
                AND (Rank_1M <= {top_50_cutoff} OR Rank_3M <= {top_50_cutoff})
            """)
            top_industries = {row[0] for row in cursor.fetchall()}
            
            # Filter candidates for industry-filtered scanners: keep only those IN a top-50% industry
            for scanner_name in INDUSTRY_FILTERED_SCANNERS:
                original_count = sum(1 for sid, _ in cache_records if sid == scanner_name)
                
                # Batch lookup industries for candidates
                filtered_tickers = [ticker for sid, ticker in cache_records if sid == scanner_name]
                if filtered_tickers:
                    placeholder = ','.join(["'"+t.replace("'","''")+"'" for t in filtered_tickers])
                    cursor.execute(f"SELECT Ticker, Industry FROM screen_data WHERE Ticker IN ({placeholder}) AND Market = '{market}'")
                    ticker_industry = {row[0]: row[1] for row in cursor.fetchall()}
                    
                    filtered_count = 0
                    new_cache = []
                    for sid, ticker in cache_records:
                        if sid == scanner_name:
                            industry = ticker_industry.get(ticker, '')
                            if industry in top_industries:
                                new_cache.append((sid, ticker))
                                filtered_count += 1
                        else:
                            new_cache.append((sid, ticker))
                    cache_records = new_cache
                    print(f"  {scanner_name}: {original_count} → {filtered_count} after industry rank top-50% filter (cutoff: rank ≤ {top_50_cutoff} of {total_industries})", flush=True)
            
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
    # Build IBD ETF Rotation Rankings (US only)
    # ---------------------------------------------------------
    if market == 'US':
        print("Computing IBD ETF Rotation Rankings...", flush=True)
        try:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ibd_etf_config.json')
            with open(config_path, 'r') as f:
                ibd_config = _json.load(f)
            
            # Build ETF lookup: ticker -> {name, sector, tier}
            etf_lookup = {}
            for s in ibd_config.get('sector_etfs', []):
                etf_lookup[s['ticker']] = {'name': s['name'], 'sector': s['gics_sector'], 'tier': 'Sector'}
            for e in ibd_config.get('industry_etfs', []):
                etf_lookup[e['ticker']] = {'name': e['name'], 'sector': e['sector'], 'tier': 'Industry'}
            
            # Fetch momentum + technical data for all ETFs from screen_data
            all_etf_tickers = list(etf_lookup.keys())
            if all_etf_tickers:
                placeholders_etf = ','.join(['%s'] * len(all_etf_tickers)) if (DATABASE_URL and DATABASE_URL.startswith('postgres')) else ','.join(['?'] * len(all_etf_tickers))
                cursor.execute(f"""
                    SELECT Ticker, Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y,
                           Pct_From_52W_High, Stage, Close, SMA_50, SMA_200
                    FROM screen_data WHERE Market = '{market}' AND Ticker IN ({placeholders_etf})
                """, all_etf_tickers)
                etf_rows = cursor.fetchall()
                
                if etf_rows:
                    cols = ['Ticker', 'm1d', 'm1w', 'm1m', 'm3m', 'm6m', 'm1y', 'pct_high', 'stage', 'close', 'sma50', 'sma200']
                    etf_df = pd.DataFrame(etf_rows, columns=cols)
                    
                    # Rank by each momentum timeframe (highest momentum = rank 1)
                    for met in ['m1d', 'm1w', 'm1m', 'm3m', 'm6m', 'm1y']:
                        etf_df[f'rank_{met}'] = etf_df[met].rank(ascending=False, method='min', na_option='bottom').fillna(9999).astype(int)
                    
                    # Build insert records
                    etf_rank_records = []
                    for _, r in etf_df.iterrows():
                        ticker = str(r['Ticker'])
                        info = etf_lookup.get(ticker, {'name': ticker, 'sector': 'Unknown', 'tier': 'Industry'})
                        close_val = float(r['close']) if pd.notna(r['close']) else None
                        sma50_val = float(r['sma50']) if pd.notna(r['sma50']) else None
                        sma200_val = float(r['sma200']) if pd.notna(r['sma200']) else None
                        above_50 = bool(close_val and sma50_val and close_val > sma50_val)
                        above_200 = bool(close_val and sma200_val and close_val > sma200_val)
                        
                        etf_rank_records.append((
                            latest_date,
                            market,
                            info['tier'],
                            ticker,
                            info['name'],
                            info['sector'],
                            int(r['rank_m1d']),
                            int(r['rank_m1w']),
                            int(r['rank_m1m']),
                            int(r['rank_m3m']),
                            int(r['rank_m6m']),
                            int(r['rank_m1y']),
                            float(r['m1d']) if pd.notna(r['m1d']) else None,
                            float(r['m1w']) if pd.notna(r['m1w']) else None,
                            float(r['m1m']) if pd.notna(r['m1m']) else None,
                            float(r['m3m']) if pd.notna(r['m3m']) else None,
                            float(r['m6m']) if pd.notna(r['m6m']) else None,
                            float(r['m1y']) if pd.notna(r['m1y']) else None,
                            float(r['pct_high']) if pd.notna(r['pct_high']) else None,
                            int(r['stage']) if pd.notna(r['stage']) else None,
                            above_50,
                            above_200
                        ))
                    
                    # Insert into ibd_etf_ranks
                    if etf_rank_records:
                        batch_size = 500
                        for i in range(0, len(etf_rank_records), batch_size):
                            batch = etf_rank_records[i:i + batch_size]
                            if DATABASE_URL and DATABASE_URL.startswith('postgres'):
                                cursor.executemany('''
                                    INSERT INTO ibd_etf_ranks (
                                        Date, Market, Tier, ETF_Ticker, ETF_Name, Sector,
                                        Rank_1D, Rank_1W, Rank_1M, Rank_3M, Rank_6M, Rank_1Y,
                                        Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y,
                                        Pct_From_52W_High, Stage, Above_50DMA, Above_200DMA
                                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                    ON CONFLICT (Date, Market, ETF_Ticker) DO UPDATE SET
                                        Tier = EXCLUDED.Tier, ETF_Name = EXCLUDED.ETF_Name, Sector = EXCLUDED.Sector,
                                        Rank_1D = EXCLUDED.Rank_1D, Rank_1W = EXCLUDED.Rank_1W,
                                        Rank_1M = EXCLUDED.Rank_1M, Rank_3M = EXCLUDED.Rank_3M,
                                        Rank_6M = EXCLUDED.Rank_6M, Rank_1Y = EXCLUDED.Rank_1Y,
                                        Momentum_1D = EXCLUDED.Momentum_1D, Momentum_1W = EXCLUDED.Momentum_1W,
                                        Momentum_1M = EXCLUDED.Momentum_1M, Momentum_3M = EXCLUDED.Momentum_3M,
                                        Momentum_6M = EXCLUDED.Momentum_6M, Momentum_1Y = EXCLUDED.Momentum_1Y,
                                        Pct_From_52W_High = EXCLUDED.Pct_From_52W_High, Stage = EXCLUDED.Stage,
                                        Above_50DMA = EXCLUDED.Above_50DMA, Above_200DMA = EXCLUDED.Above_200DMA
                                ''', batch)
                            else:
                                cursor.executemany('''
                                    INSERT OR REPLACE INTO ibd_etf_ranks (
                                        Date, Market, Tier, ETF_Ticker, ETF_Name, Sector,
                                        Rank_1D, Rank_1W, Rank_1M, Rank_3M, Rank_6M, Rank_1Y,
                                        Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y,
                                        Pct_From_52W_High, Stage, Above_50DMA, Above_200DMA
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', batch)
                            conn.commit()
                        print(f"Computed and inserted {len(etf_rank_records)} IBD ETF rotation rankings.", flush=True)
                else:
                    print("No ETF momentum data found in screen_data for IBD ranking.", flush=True)
        except FileNotFoundError:
            print("Warning: ibd_etf_config.json not found. Skipping IBD ETF rankings.", flush=True)
        except Exception as e:
            print(f"Warning: IBD ETF ranking computation failed: {e}", flush=True)

    # ---------------------------------------------------------
    # Post-compute: Leading Industry + Leading Stock scanner
    # (This scanner depends on ibd_etf_ranks, which was just populated)
    # ---------------------------------------------------------
    if market == 'US':
        print("Post-computing Leading Industry + Leading Stock scanner...", flush=True)
        try:
            etf_date_q = f"SELECT MAX(Date) FROM ibd_etf_ranks WHERE Market = '{market}'"
            lis_condition = (
                "d.Stage = 2 "
                "AND d.RS_Rating >= 85 "
                "AND d.Close >= 10 "
                "AND d.IBD_ETF_Proxy IS NOT NULL "
                "AND etf.Rank_3M <= 20 "
                "AND etf.Above_50DMA IS TRUE"
            )
            cursor.execute(f"""
                SELECT d.Ticker FROM screen_data d
                LEFT JOIN fundamentals_data f ON d.Ticker = f.Ticker
                LEFT JOIN ibd_etf_ranks etf ON d.IBD_ETF_Proxy = etf.ETF_Ticker AND etf.Market = '{market}' AND etf.Date = ({etf_date_q})
                WHERE d.Market = '{market}' AND d.{baseline} AND ({lis_condition})
            """)
            lis_matches = cursor.fetchall()
            lis_records = [('leading-industry-stock', row[0] if isinstance(row, tuple) else row.get('Ticker', row[0])) for row in lis_matches]
            if lis_records:
                batch_size = 500
                for i in range(0, len(lis_records), batch_size):
                    batch = lis_records[i:i + batch_size]
                    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
                        cursor.executemany(f"INSERT INTO scanner_results (scanner_id, Ticker, Market) VALUES (%s, %s, '{market}')", batch)
                    else:
                        cursor.executemany(f"INSERT INTO scanner_results (scanner_id, Ticker, Market) VALUES (?, ?, '{market}')", batch)
                conn.commit()
            print(f"  Leading Industry + Leading Stock: {len(lis_records)} matches", flush=True)
        except Exception as e:
            print(f"Warning: Leading Industry scanner post-compute failed: {e}", flush=True)

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
    # Also clean old IBD ETF ranks
    cursor.execute(f'''
        DELETE FROM ibd_etf_ranks 
        WHERE Market = '{market}' AND Date NOT IN (
            SELECT DISTINCT Date 
            FROM ibd_etf_ranks 
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

    # Portfolio simulation is run separately (via GitHub Actions schedule or manual trigger).
    # Uncomment below to re-enable inline simulation after ingestion.
    # print(f"[{market}] Running portfolio simulation...", flush=True)
    # if market == 'US':
    #     try:
    #         from api.services.portfolio_engine import run_all_variants, store_results
    #         results = run_all_variants(in_memory_data=sim_data_dict)
    #         if results:
    #             store_results(results)
    #             print("✅ Successfully updated portfolio simulation results.", flush=True)
    #         else:
    #             print("⚠️ Portfolio Simulation yielded no data.", flush=True)
    #     except Exception as e:
    #         print(f"❌ Portfolio Simulation Error: {e}", flush=True)

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
