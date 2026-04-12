"""
Portfolio Simulation Engine — US Market
========================================
Runs 16 parallel strategy variants on daily OHLCV data producing:
- Complete trade audit trail
- Daily equity curve
- Champion-grade trading statistics (Zanger / Darvas style)

First 8 variants: Original RS-ranked entry selection (highest RS gets priority)
Last 8 variants: ATH-proximity ranked entry selection (closest to 52W high gets priority, RS as tiebreaker)

All "DMA" = SMA (Simple Moving Average) — confirmed in spec v0.2.
Entry at T+1 Open after signal on T. InitialStop = previous bar's StopLine.

Version: 1.0.0
"""

import json
import time
import datetime
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict, deque

import pandas as pd
import numpy as np

from api.database import get_db

import os

# ──────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────
STARTING_CAPITAL = 100_000.0
MAX_POSITIONS = 4
# Dynamic: computed from data. Legacy fallback only.
SIM_START_DATE = "2020-01-01"
# Configurable lookback period (change to 1, 3, or 5 years anytime)
SIM_LOOKBACK_YEARS = int(os.environ.get('SIM_LOOKBACK_YEARS', '5'))
EMA_PERIOD = 8
RS_THRESHOLD = 97
MIN_PRICE = 10.0
MIN_AVG_DOLLAR_VOL = 5_000_000.0  # $5M/day
PULLBACK_PCT = 0.02  # 2% pullback filter
VERSION = "1.2.0"

# Championship (E3) Constants
HARD_STOP_PCT = 0.08       # 8% hard max loss from entry price
ATR_RISK_PCT = 0.02        # Risk 2% of equity per trade (optimized via sweep)
MAX_POSITION_PCT = 0.33    # Max 33% of equity in any single position

# Strategy Variant Definitions
# First 8: Original RS-ranked entry selection
# Next 8: ATH-proximity ranked entry selection
# Last 2: Championship variants (ATR sizing + hard stop)
VARIANTS = [
    # Original 8 variants (RS-ranked)
    {"id": "G1_R1_E1", "label": "QQQ>21>50>200 · IBD RS≥97 · Scale+BE",  "gate_sma": 21, "rs_mode": "ibd",  "exit": "E1", "rank_by": "rs"},
    {"id": "G1_R1_E2", "label": "QQQ>21>50>200 · IBD RS≥97 · Pure Ride", "gate_sma": 21, "rs_mode": "ibd",  "exit": "E2", "rank_by": "rs"},
    {"id": "G1_R2_E1", "label": "QQQ>21>50>200 · 1M RS≥97 · Scale+BE",   "gate_sma": 21, "rs_mode": "1m",   "exit": "E1", "rank_by": "rs"},
    {"id": "G1_R2_E2", "label": "QQQ>21>50>200 · 1M RS≥97 · Pure Ride",  "gate_sma": 21, "rs_mode": "1m",   "exit": "E2", "rank_by": "rs"},
    {"id": "G1_R2_E1_MB", "label": "QQQ>21>50>200 · 1M RS≥97 · Mod. Breakout",  "gate_sma": 21, "rs_mode": "1m", "exit": "E1", "filter": "modern_breakout", "rank_by": "rs"},
    {"id": "G1_R2_E1_MP", "label": "QQQ>21>50>200 · 1M RS≥97 · Mod. Pullback",  "gate_sma": 21, "rs_mode": "1m", "exit": "E1", "filter": "modern_pullback", "rank_by": "rs"},
    {"id": "G1_R2_E1_EP", "label": "QQQ>21>50>200 · 1M RS≥97 · Mod. EP", "gate_sma": 21, "rs_mode": "1m", "exit": "E1", "filter": "modern_ep", "rank_by": "rs"},
    {"id": "G1_R2_E2_EP", "label": "QQQ>21>50>200 · 1M RS≥97 · Mod. EP Pure", "gate_sma": 21, "rs_mode": "1m", "exit": "E2", "filter": "modern_ep", "rank_by": "rs"},
    
    # 8 ATH-proximity ranked variants
    {"id": "G1_R1_E1_ATH", "label": "QQQ>21>50>200 · IBD RS≥97 · Scale+BE · ATH Priority",  "gate_sma": 21, "rs_mode": "ibd",  "exit": "E1", "rank_by": "ath"},
    {"id": "G1_R1_E2_ATH", "label": "QQQ>21>50>200 · IBD RS≥97 · Pure Ride · ATH Priority", "gate_sma": 21, "rs_mode": "ibd",  "exit": "E2", "rank_by": "ath"},
    {"id": "G1_R2_E1_ATH", "label": "QQQ>21>50>200 · 1M RS≥97 · Scale+BE · ATH Priority",   "gate_sma": 21, "rs_mode": "1m",   "exit": "E1", "rank_by": "ath"},
    {"id": "G1_R2_E2_ATH", "label": "QQQ>21>50>200 · 1M RS≥97 · Pure Ride · ATH Priority",  "gate_sma": 21, "rs_mode": "1m",   "exit": "E2", "rank_by": "ath"},
    {"id": "G1_R2_E1_MB_ATH", "label": "QQQ>21>50>200 · 1M RS≥97 · Mod. Breakout · ATH Priority",  "gate_sma": 21, "rs_mode": "1m", "exit": "E1", "filter": "modern_breakout", "rank_by": "ath"},
    {"id": "G1_R2_E1_MP_ATH", "label": "QQQ>21>50>200 · 1M RS≥97 · Mod. Pullback · ATH Priority",  "gate_sma": 21, "rs_mode": "1m", "exit": "E1", "filter": "modern_pullback", "rank_by": "ath"},
    {"id": "G1_R2_E1_EP_ATH", "label": "QQQ>21>50>200 · 1M RS≥97 · Mod. EP · ATH Priority", "gate_sma": 21, "rs_mode": "1m", "exit": "E1", "filter": "modern_ep", "rank_by": "ath"},
    {"id": "G1_R2_E2_EP_ATH", "label": "QQQ>21>50>200 · 1M RS≥97 · Mod. EP Pure · ATH Priority", "gate_sma": 21, "rs_mode": "1m", "exit": "E2", "filter": "modern_ep", "rank_by": "ath"},

    # Championship variants: ATR-based sizing (risk 1% per trade) + 8% hard stop + Pure Ride trailing
    {"id": "G1_R2_E3", "label": "QQQ>21>50>200 · 1M RS≥97 · Championship",  "gate_sma": 21, "rs_mode": "1m", "exit": "E3", "rank_by": "rs", "sizing": "atr"},
    {"id": "G1_R2_E3_ATH", "label": "QQQ>21>50>200 · 1M RS≥97 · Championship · ATH Priority",  "gate_sma": 21, "rs_mode": "1m", "exit": "E3", "rank_by": "ath", "sizing": "atr"},
]


# ──────────────────────────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────────────────────────
def load_ohlcv_data() -> Dict[str, pd.DataFrame]:
    """Load historical OHLCV data directly into a bulk DataFrame for massive memory savings."""
    print("   -> Fetching raw rows from DB...", flush=True)
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT Ticker, Date, Open, High, Low, Close, Volume
            FROM daily_ohlcv
            WHERE Market = 'US' AND Date >= '2020-01-01'
        """
        cursor.execute(query)
        # fetchall() natively returns list of tuples for psycopg2 and standard sqlite3.
        # This is strictly Memory-Optimized (no Python dict overhead).
        rows = cursor.fetchall()

    print(f"   -> DB fetch complete ({len(rows)} rows). Converting to bulk DataFrame...", flush=True)
    columns = ['Ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    df = pd.DataFrame(rows, columns=columns)
    
    # 🚨 Crucial: Free the raw tuple list from Python memory!
    del rows
    
    print("   -> Normalizing types...", flush=True)
    df['Date'] = pd.to_datetime(df['Date'])
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    df = df.dropna(subset=['Close'])

    print("   -> Splitting and computing indicators per ticker...", flush=True)
    result = {}
    for ticker, group in df.groupby('Ticker'):
        group = group.sort_values('Date').reset_index(drop=True)
        if len(group) >= 30:  # Need minimum history for indicators
            # Apply indicators at the source
            result[ticker] = compute_indicators(group)

    return result


def load_rs_ratings() -> Dict[str, float]:
    """Load latest RS_Rating from screen_data for IBD-style RS check."""
    with get_db() as conn:
        is_pg = hasattr(conn, 'info') or hasattr(conn, 'dsn')
        cursor = conn.cursor()
        query = "SELECT Ticker, RS_Rating FROM screen_data WHERE Market = 'US' AND RS_Rating IS NOT NULL"
        if is_pg:
            cursor.execute(query)
            cols = [desc[0] for desc in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        else:
            import sqlite3
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            rows = [dict(r) for r in cursor.fetchall()]

    return {(r.get('Ticker') or r.get('ticker')): float(r.get('RS_Rating') or r.get('rs_rating') or 0)
            for r in rows}


# ──────────────────────────────────────────────────────────────────
# Indicator Computation
# ──────────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add 8 EMA triple structure, StopLine, SMA 21/50, and liquidity columns."""
    df = df.copy()

    # 8 EMA triple structure (Pine Script style)
    df['EMA_High_8'] = df['High'].ewm(span=EMA_PERIOD, adjust=False).mean()
    df['EMA_Close_8'] = df['Close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    df['EMA_Low_8'] = df['Low'].ewm(span=EMA_PERIOD, adjust=False).mean()

    # StopLine = EMA of Lows (8)
    df['StopLine'] = df['EMA_Low_8']

    # Bullish structure: Close > all three EMAs
    df['Bullish_Structure'] = (
        (df['Close'] > df['EMA_High_8']) &
        (df['Close'] > df['EMA_Close_8']) &
        (df['Close'] > df['EMA_Low_8'])
    )

    # Pullback filter: Close within 2% of EMA High cluster
    df['Pullback_OK'] = df['Close'] <= df['EMA_High_8'] * (1 + PULLBACK_PCT)

    # SMA 21 and SMA 50 (for QQQ gate — applied to QQQ's DataFrame)
    df['SMA_21'] = df['Close'].rolling(window=21).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()

    # Avg Dollar Volume (50-day) for liquidity filter
    df['Dollar_Volume'] = df['Close'] * df['Volume']
    df['Avg_Dollar_Vol_50'] = df['Dollar_Volume'].rolling(window=50).mean()

    # Pre-shift StopLine for initial stop access (T-1)
    df['Prev_StopLine'] = df['StopLine'].shift(1)

    # ── Advanced Indicators for Modern Scanners ──
    df['SMA_10'] = df['Close'].rolling(window=10).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_150'] = df['Close'].rolling(window=150).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()

    df['SMA_200_Up'] = df['SMA_200'] > df['SMA_200'].shift(20)
    df['In_Stage_2'] = (df['Close'] > df['SMA_150']) & (df['SMA_150'] > df['SMA_200']) & df['SMA_200_Up']

    df['52W_High'] = df['High'].rolling(252).max()
    df['Pct_From_52W_High'] = ((df['Close'] - df['52W_High']) / df['52W_High'].replace(0, np.nan)) * 100

    df['Volume_SMA_50'] = df['Volume'].rolling(50).mean()
    df['RVOL'] = df['Volume'] / df['Volume_SMA_50'].replace(0, np.nan)

    avg_10d_range = df['High'].rolling(10).max() - df['Low'].rolling(10).min()
    today_range = df['High'] - df['Low']
    df['VCP_Approximation'] = (today_range < (0.3 * avg_10d_range)) & (df['Volume'] < df['Volume_SMA_50'])

    df['Inside_Bar'] = (df['High'] < df['High'].shift(1)) & (df['Low'] > df['Low'].shift(1))

    rolling_min = df['Close'].rolling(4).min()
    df['Tight_Setup'] = ((df['Close'].rolling(4).max() - rolling_min) / rolling_min.replace(0, np.nan)) < 0.02

    df['Gap_Up_Pct'] = (df['Open'] / df['Close'].shift(1).replace(0, np.nan)) - 1.0

    df['Is_Modern_Breakout'] = (
        df['In_Stage_2'] & 
        (df['Pct_From_52W_High'] > -20) & 
        (df['Tight_Setup'] | df['VCP_Approximation'] | df['Inside_Bar']) & 
        (abs(df['Close'] - df['SMA_20']) / df['SMA_20'].replace(0, np.nan) <= 0.06) &
        (df['RVOL'] > 1.5)
    )

    df['Is_Modern_Pullback'] = (
        df['In_Stage_2'] & 
        (df['Close'] >= df['SMA_50']) & 
        (df['SMA_20'] >= df['SMA_50']) & 
        (df['RVOL'] < 1.0) & 
        ((abs(df['Close'] - df['SMA_20']) / df['SMA_20'].replace(0, np.nan) <= 0.02) | (abs(df['Close'] - df['SMA_10']) / df['SMA_10'].replace(0, np.nan) <= 0.02)) & 
        (df['Inside_Bar'] | df['Tight_Setup'] | df['VCP_Approximation'])
    )

    df['Is_Episodic_Pivot'] = (
        df['In_Stage_2'] &
        (df['Gap_Up_Pct'] > 0.05) &
        (df['RVOL'] > 3.0)
    )

    return df


def compute_rolling_rs_percentiles(all_data: Dict[str, pd.DataFrame], spy_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Compute ROLLING cross-sectional RS percentile rankings for EVERY trading date.
    This eliminates lookahead bias by ensuring each date only uses data available up to that date.

    Produces two columns per ticker DataFrame:
      - '1M_RS_Pctile':  1-month (21d) RS vs SPY, ranked across universe (0-100)
      - 'IBD_RS_Pctile': IBD-style composite RS (weighted multi-timeframe), ranked across universe (0-99)

    IBD composite formula: 40% * Q1_perf + 20% * Q2_perf + 20% * Q3_perf + 20% * Q4_perf
    where Q1 = most recent 63 days, Q2 = days 64-126, Q3 = days 127-189, Q4 = days 190-252.
    Each is computed as (stock_return / spy_return) for that period.
    """
    spy_close = spy_df.set_index('Date')['Close']
    if isinstance(spy_close, pd.DataFrame):
        spy_close = spy_close.iloc[:, 0]

    # ── 1M RS (21d) ratios ──
    spy_ret_21 = spy_close / spy_close.shift(21)

    # ── IBD composite: quarterly returns for weighted score ──
    # Q1 = most recent 63 days performance
    spy_ret_q1 = spy_close / spy_close.shift(63)
    # Q2 = performance from day 126 back to day 63 ago (i.e. shift(126)/shift(63))
    spy_ret_q2 = spy_close.shift(63) / spy_close.shift(126)
    # Q3 = performance from day 189 back to day 126  
    spy_ret_q3 = spy_close.shift(126) / spy_close.shift(189)
    # Q4 = performance from day 252 back to day 189
    spy_ret_q4 = spy_close.shift(189) / spy_close.shift(252)

    index_tickers = {'SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLY', 'XLV',
                     'XLE', 'XLI', 'XLC', 'XLU', 'XLP', 'XLRE', 'XLB'}

    ticker_1m_ratios: Dict[str, pd.Series] = {}
    ticker_ibd_scores: Dict[str, pd.Series] = {}

    for ticker, df in all_data.items():
        if ticker in index_tickers:
            continue

        ts = df.set_index('Date')['Close']
        if isinstance(ts, pd.DataFrame):
            ts = ts.iloc[:, 0]

        # ── 1M ratio ──
        stock_ret_21 = ts / ts.shift(21)
        ratio_1m = stock_ret_21 / spy_ret_21.reindex(stock_ret_21.index)
        ratio_1m = ratio_1m.dropna()
        if len(ratio_1m) > 0:
            ticker_1m_ratios[ticker] = ratio_1m

        # ── IBD composite ──
        s_q1 = ts / ts.shift(63)
        s_q2 = ts.shift(63) / ts.shift(126)
        s_q3 = ts.shift(126) / ts.shift(189)
        s_q4 = ts.shift(189) / ts.shift(252)

        # Relative to SPY for each quarter
        r_q1 = s_q1 / spy_ret_q1.reindex(s_q1.index)
        r_q2 = s_q2 / spy_ret_q2.reindex(s_q2.index)
        r_q3 = s_q3 / spy_ret_q3.reindex(s_q3.index)
        r_q4 = s_q4 / spy_ret_q4.reindex(s_q4.index)

        # Weighted composite (IBD weights most recent quarter heaviest)
        ibd_raw = 0.4 * r_q1 + 0.2 * r_q2 + 0.2 * r_q3 + 0.2 * r_q4
        ibd_raw = ibd_raw.dropna()
        if len(ibd_raw) > 0:
            ticker_ibd_scores[ticker] = ibd_raw

    print(f"   📈 Computing rolling RS for {len(ticker_1m_ratios)} tickers (1M) and {len(ticker_ibd_scores)} tickers (IBD)...", flush=True)

    # ── Cross-sectional percentile ranking per date ──
    # 1M percentiles
    if ticker_1m_ratios:
        combined_1m = pd.DataFrame(ticker_1m_ratios)
        pctiles_1m = combined_1m.rank(axis=1, pct=True) * 100
    else:
        pctiles_1m = pd.DataFrame()

    # IBD percentiles (0-99 scale to match IBD convention)
    if ticker_ibd_scores:
        combined_ibd = pd.DataFrame(ticker_ibd_scores)
        pctiles_ibd = combined_ibd.rank(axis=1, pct=True) * 99
    else:
        pctiles_ibd = pd.DataFrame()

    # ── Merge back into each ticker's DataFrame ──
    for ticker, df in all_data.items():
        df_indexed = df.set_index('Date')

        if ticker in pctiles_1m.columns:
            df_indexed['1M_RS_Pctile'] = pctiles_1m[ticker]
        else:
            df_indexed['1M_RS_Pctile'] = np.nan

        if ticker in pctiles_ibd.columns:
            df_indexed['IBD_RS_Pctile'] = pctiles_ibd[ticker]
        else:
            df_indexed['IBD_RS_Pctile'] = np.nan

        all_data[ticker] = df_indexed.reset_index()

    return all_data


def precompute_signals(all_data: Dict[str, pd.DataFrame]) -> Dict[str, List[dict]]:
    """
    Vectorized filter to find all valid entry candidates upfront.
    Uses per-date rolling RS percentiles (no lookahead bias).
    Returns: dict mapping date string -> list of candidate dicts.
    """
    signals_by_date = defaultdict(list)
    print("   🚀 Precomputing vectorized entry signals (lookahead-free)...", flush=True)

    index_tickers = {'SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLY', 'XLV',
                     'XLE', 'XLI', 'XLC', 'XLU', 'XLP', 'XLRE', 'XLB'}

    for ticker, df in all_data.items():
        if ticker in index_tickers:
            continue

        ibd_rs_col = df.get('IBD_RS_Pctile', pd.Series(0, index=df.index))
        rs_1m_col = df.get('1M_RS_Pctile', pd.Series(0, index=df.index))

        # Vectorized logical mask — RS threshold now uses rolling per-date values
        mask = (
            (df['Close'] >= MIN_PRICE) &
            (df['Avg_Dollar_Vol_50'] >= MIN_AVG_DOLLAR_VOL) &
            (df['Close'] > df['StopLine']) &
            ((ibd_rs_col >= RS_THRESHOLD) | (rs_1m_col >= RS_THRESHOLD)) &
            (
                ((df['Bullish_Structure'] == True) & (df['Pullback_OK'] == True)) |
                (df['Is_Modern_Breakout'] == True) |
                (df['Is_Modern_Pullback'] == True) |
                (df['Is_Episodic_Pivot'] == True)
            )
        )

        valid_df = df[mask]
        if valid_df.empty:
            continue

        for _, row in valid_df.iterrows():
            date_val = row['Date']
            if isinstance(date_val, pd.Timestamp):
                date_str = date_val.strftime('%Y-%m-%d')
            else:
                date_str = str(date_val)

            pctile_1m = row.get('1M_RS_Pctile', np.nan)
            pctile_ibd = row.get('IBD_RS_Pctile', np.nan)
            initial_stop = float(row.get('Prev_StopLine', np.nan))

            if pd.isna(initial_stop) or initial_stop <= 0:
                continue

            # Calculate distance from 52W high (for ATH-proximity ranking)
            pct_from_52w_high = row.get('Pct_From_52W_High', np.nan)
            if pd.isna(pct_from_52w_high):
                pct_from_52w_high = -100.0  # Default to far from high if not available

            signals_by_date[date_str].append({
                "ticker": ticker,
                "close": float(row['Close']),
                "initial_stop": initial_stop,
                "rs_ibd": float(pctile_ibd) if not pd.isna(pctile_ibd) else 0,
                "rs_1m": float(pctile_1m) if not pd.isna(pctile_1m) else 0,
                "ema_high_8": float(row['EMA_High_8']),
                "pct_from_52w_high": float(pct_from_52w_high),
                "is_standard": bool(row['Bullish_Structure'] and row['Pullback_OK']),
                "is_m_breakout": bool(row.get('Is_Modern_Breakout', False)),
                "is_m_pullback": bool(row.get('Is_Modern_Pullback', False)),
                "is_ep": bool(row.get('Is_Episodic_Pivot', False))
            })

    return dict(signals_by_date)


# ──────────────────────────────────────────────────────────────────
# Position & Trade Tracking
# ──────────────────────────────────────────────────────────────────
class Position:
    """Tracks a single open position."""
    __slots__ = [
        'ticker', 'entry_date', 'entry_price', 'shares', 'initial_shares',
        'initial_stop', 'R', 'has_scaled', 'stop_moved_to_be',
        'exit_system', 'reason', 'realized_pnl', 'partial_shares_sold'
    ]

    def __init__(self, ticker: str, entry_date: str, entry_price: float,
                 shares: int, initial_stop: float, exit_system: str, reason: str):
        self.ticker = ticker
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.shares = shares
        self.initial_shares = shares
        self.initial_stop = initial_stop
        self.R = entry_price - initial_stop  # Must be > 0
        self.has_scaled = False
        self.stop_moved_to_be = False
        self.exit_system = exit_system
        self.reason = reason
        self.realized_pnl = 0.0  # Accumulates PnL from partial exits
        self.partial_shares_sold = 0  # Track how many shares sold in partials


def make_trade_record(date: str, ticker: str, action: str, qty: int,
                      price: float, pnl: float, r_multiple: float,
                      cumulative_equity: float, reason: str) -> dict:
    """Create a standardized trade record."""
    return {
        "date": date,
        "ticker": ticker,
        "action": action,
        "qty": qty,
        "price": round(price, 2),
        "fees": 0.0,
        "pnl": round(pnl, 2),
        "r_multiple": round(r_multiple, 4) if r_multiple is not None else None,
        "cumulative_equity": round(cumulative_equity, 2),
        "reason": reason
    }


# ──────────────────────────────────────────────────────────────────
# Simulation Core
# ──────────────────────────────────────────────────────────────────
def run_variant(variant: dict, all_data: Dict[str, pd.DataFrame],
                qqq_df: pd.DataFrame, signals_by_date: Dict[str, List[dict]],
                trading_dates: List[str]) -> dict:
    """
    Run a single variant simulation day-by-day.
    Returns the full result dict for this variant.
    """
    gate_sma = variant["gate_sma"]
    rs_mode = variant["rs_mode"]
    exit_system = variant["exit"]
    variant_id = variant["id"]
    variant_label = variant["label"]
    rank_by = variant.get("rank_by", "rs")  # Default to RS ranking for backward compatibility
    variant_filter = variant.get("filter", None)
    sizing_mode = variant.get("sizing", "fixed")  # "fixed" (25% alloc) or "atr" (risk 1% per trade)

    # Pre-compute QQQ gate series
    qqq_indexed = qqq_df  # Now already indexed by Date
    sma_col = f'SMA_{gate_sma}'

    # State
    cash = STARTING_CAPITAL
    positions: List[Position] = []
    trades: List[dict] = []
    equity_curve: List[dict] = []
    gate_history: List[dict] = []
    events_log: List[dict] = []
    closed_trades_for_stats: List[dict] = []

    # Pending entries: signals generated on day T, executed on T+1 open
    pending_entries: List[dict] = []
    
    # Dynamic Progressive Exposure: track last 5 R-multiples to adapt allocation size
    recent_rs = deque(maxlen=5)

    def get_dynamic_weight() -> float:
        if len(recent_rs) < 5:
            return 0.25
        sum_r = sum(recent_rs)
        if sum_r < -2.0:
            return 0.10  # Cold streak: reduce to 10%
        elif sum_r > 2.0:
            return 0.35  # Hot streak: expand to 35%
        return 0.25

    def get_equity(date_str: str) -> float:
        """Calculate total equity = cash + sum of position market values."""
        total = cash
        for pos in positions:
            if pos.ticker in all_data:
                df = all_data[pos.ticker]
                try:
                    row = df.loc[date_str]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    total += pos.shares * float(row['Close'])
                except KeyError:
                    total += pos.shares * pos.entry_price
            else:
                total += pos.shares * pos.entry_price
        return total

    def get_ticker_row(ticker: str, date_str: str) -> Optional[pd.Series]:
        """Get a ticker's data row for a specific date (O(1) index lookup)."""
        if ticker not in all_data:
            return None
        df = all_data[ticker]
        try:
            row = df.loc[date_str]
            if isinstance(row, pd.DataFrame):
                return row.iloc[0]
            return row
        except KeyError:
            return None

    for i, date_str in enumerate(trading_dates):

        # ── Step 1: Check QQQ Gate (Strict Market Regime) ──
        qqq_row = None
        if date_str in qqq_indexed.index:
            qqq_row = qqq_indexed.loc[date_str]
            
        gate_on = False
        c, s21 = None, None
        
        if qqq_row is not None:
            c = float(qqq_row.get('Close', 0))
            s21 = float(qqq_row.get('SMA_21', np.nan))
            s50 = float(qqq_row.get('SMA_50', np.nan))
            s200 = float(qqq_row.get('SMA_200', np.nan))
            
            if pd.notna(s21) and pd.notna(s50) and pd.notna(s200):
                gate_on = (c > s21) and (s21 > s50) and (s50 > s200)

        gate_history.append({
            "date": date_str,
            "gate_on": gate_on,
            "qqq_close": round(c, 2) if c is not None else None,
            "qqq_sma": round(s21, 2) if pd.notna(s21) else None
        })

        # ── Step 2: Execute Pending Entries (from yesterday's signals) ──
        new_pending = []
        for entry in pending_entries:
            ticker = entry['ticker']
            row = get_ticker_row(ticker, date_str)
            if row is None:
                continue  # No data for this day, skip

            entry_price = float(row['Open'])
            if entry_price <= 0:
                continue

            initial_stop = entry['initial_stop']
            if entry_price <= initial_stop or (entry_price - initial_stop) < 0.01:
                # Invalid risk — skip (R must be at least $0.01)
                events_log.append({"date": date_str, "event": f"Skipped {ticker}: entry {entry_price:.2f} <= stop {initial_stop:.2f} (insufficient R)"})
                continue

            # Position sizing
            current_equity = get_equity(date_str)
            risk_per_share = entry_price - initial_stop  # = R

            if sizing_mode == "atr":
                # Championship: risk exactly ATR_RISK_PCT (1%) of equity per trade
                dollar_risk = current_equity * ATR_RISK_PCT
                shares = int(dollar_risk / risk_per_share) if risk_per_share > 0 else 0
                # Cap at MAX_POSITION_PCT of equity
                max_shares = int(current_equity * MAX_POSITION_PCT / entry_price)
                shares = min(shares, max_shares)
            else:
                # Standard: fixed allocation based on progressive exposure
                alloc = current_equity * get_dynamic_weight()
                shares = int(alloc / entry_price)

            if shares <= 0:
                continue

            cost = shares * entry_price
            if cost > cash:
                shares = int(cash / entry_price)
                if shares <= 0:
                    continue
                cost = shares * entry_price

            cash -= cost
            reason = entry['reason']
            pos = Position(ticker, date_str, entry_price, shares, initial_stop, exit_system, reason)
            positions.append(pos)

            cum_eq = get_equity(date_str)
            trades.append(make_trade_record(
                date_str, ticker, "BUY", shares, entry_price,
                0.0, None, cum_eq, reason
            ))

        pending_entries = new_pending

        # ── Step 3: Manage Existing Positions ──
        positions_to_remove = []
        for pos in positions:
            row = get_ticker_row(pos.ticker, date_str)
            if row is None:
                continue

            close = float(row['Close'])
            low = float(row['Low'])
            stop_line = float(row['StopLine']) if pd.notna(row.get('StopLine')) else None

            if stop_line is None:
                continue

            # ── E1: Scale at 3R + Breakeven Runner ──
            if pos.exit_system == "E1":
                try:
                    unrealized_per_share = close - pos.entry_price

                    # Check if 3R reached and we haven't scaled yet
                    if not pos.has_scaled and pos.R > 0 and unrealized_per_share >= 3 * pos.R:
                        sell_shares = max(1, pos.initial_shares // 3)
                        sell_shares = min(sell_shares, pos.shares)
                        pnl = sell_shares * (close - pos.entry_price)
                        r_mult = unrealized_per_share / pos.R if pos.R > 0 else 0

                        # Track partial exit PnL for accurate statistics
                        pos.realized_pnl += pnl
                        pos.partial_shares_sold += sell_shares
                        pos.shares -= sell_shares
                        cash += sell_shares * close
                        pos.has_scaled = True
                        pos.stop_moved_to_be = True  # Move stop to breakeven

                        cum_eq = get_equity(date_str)
                        trades.append(make_trade_record(
                            date_str, pos.ticker, "PARTIAL", sell_shares, close,
                            pnl, r_mult, cum_eq,
                            f"3R profit reached ({unrealized_per_share / pos.R:.1f}R). Sold 1/3, stop moved to breakeven." if pos.R > 0 else "3R profit reached. Sold 1/3, stop moved to breakeven."
                        ))
                        
                        if pos.shares == 0:
                            # All shares sold via partial — record total PnL
                            total_pnl = pos.realized_pnl
                            total_r = total_pnl / (pos.initial_shares * pos.R) if pos.R > 0 else 0
                            closed_trades_for_stats.append({
                                "ticker": pos.ticker, "entry_date": pos.entry_date,
                                "exit_date": date_str, "entry_price": pos.entry_price,
                                "exit_price": close, "shares": pos.initial_shares,
                                "pnl": total_pnl, "r_multiple": total_r,
                                "holding_days": (pd.Timestamp(date_str) - pd.Timestamp(pos.entry_date)).days,
                                "exit_type": "scaled_full"
                            })
                            recent_rs.append(total_r)
                            positions_to_remove.append(pos)
                except Exception as e:
                    print(f"   ⚠️  Error in E1 exit for {pos.ticker} on {date_str}: {e} (pos.R={pos.R}, close={close}, entry={pos.entry_price})", flush=True)
                    raise

                # After scaling, check exits with precedence: structural first
                if pos.has_scaled and pos.shares > 0:
                    # Structural exit: Close < StopLine
                    if close < stop_line:
                        remaining_pnl = pos.shares * (close - pos.entry_price)
                        total_pnl = pos.realized_pnl + remaining_pnl
                        total_r = total_pnl / (pos.initial_shares * pos.R) if pos.R > 0 else 0
                        cash += pos.shares * close
                        cum_eq = get_equity(date_str)

                        closed_trades_for_stats.append({
                            "ticker": pos.ticker, "entry_date": pos.entry_date,
                            "exit_date": date_str, "entry_price": pos.entry_price,
                            "exit_price": close, "shares": pos.initial_shares,
                            "pnl": total_pnl, "r_multiple": total_r,
                            "holding_days": (pd.Timestamp(date_str) - pd.Timestamp(pos.entry_date)).days,
                            "exit_type": "structural_after_partial"
                        })

                        trades.append(make_trade_record(
                            date_str, pos.ticker, "SELL", pos.shares, close,
                            remaining_pnl, (close - pos.entry_price) / pos.R if pos.R > 0 else 0, cum_eq,
                            f"Final structural exit (post-scale): Close {close:.2f} < StopLine {stop_line:.2f}"
                        ))
                        recent_rs.append(total_r)
                        positions_to_remove.append(pos)
                        continue

                    # Breakeven stop: Low <= EntryPrice (intraday)
                    elif pos.stop_moved_to_be and low <= pos.entry_price:
                        open_price = float(row['Open'])
                        # If it gapped down past our entry, we suffer slippage to the open price.
                        exit_price = pos.entry_price if open_price >= pos.entry_price else open_price
                        remaining_pnl = pos.shares * (exit_price - pos.entry_price)
                        total_pnl = pos.realized_pnl + remaining_pnl
                        total_r = total_pnl / (pos.initial_shares * pos.R) if pos.R > 0 else 0.0
                        cash += pos.shares * exit_price
                        cum_eq = get_equity(date_str)

                        closed_trades_for_stats.append({
                            "ticker": pos.ticker, "entry_date": pos.entry_date,
                            "exit_date": date_str, "entry_price": pos.entry_price,
                            "exit_price": exit_price, "shares": pos.initial_shares,
                            "pnl": total_pnl, "r_multiple": total_r,
                            "holding_days": (pd.Timestamp(date_str) - pd.Timestamp(pos.entry_date)).days,
                            "exit_type": "breakeven_stop"
                        })

                        trades.append(make_trade_record(
                            date_str, pos.ticker, "STOP", pos.shares, exit_price,
                            remaining_pnl, (exit_price - pos.entry_price) / pos.R if pos.R > 0 else 0, cum_eq,
                            f"Breakeven stop hit: Low {low:.2f} <= Entry {pos.entry_price:.2f}"
                        ))
                        recent_rs.append(total_r)
                        positions_to_remove.append(pos)
                        continue

                # Before 3R: structural exit only
                elif not pos.has_scaled and close < stop_line:
                    pnl = pos.shares * (close - pos.entry_price)
                    r_mult = (close - pos.entry_price) / pos.R if pos.R > 0 else 0
                    cash += pos.shares * close
                    cum_eq = get_equity(date_str)

                    closed_trades_for_stats.append({
                        "ticker": pos.ticker, "entry_date": pos.entry_date,
                        "exit_date": date_str, "entry_price": pos.entry_price,
                        "exit_price": close, "shares": pos.initial_shares,
                        "pnl": pnl, "r_multiple": r_mult,
                        "holding_days": (pd.Timestamp(date_str) - pd.Timestamp(pos.entry_date)).days,
                        "exit_type": "structural_full"
                    })

                    trades.append(make_trade_record(
                        date_str, pos.ticker, "SELL", pos.shares, close,
                        pnl, r_mult, cum_eq,
                        f"Structural exit (pre-3R): Close {close:.2f} < StopLine {stop_line:.2f}"
                    ))
                    recent_rs.append(r_mult)
                    positions_to_remove.append(pos)
                    continue

            # ── E2: Pure Ride ──
            elif pos.exit_system == "E2":
                if close < stop_line:
                    pnl = pos.shares * (close - pos.entry_price)
                    r_mult = (close - pos.entry_price) / pos.R if pos.R > 0 else 0
                    cash += pos.shares * close
                    cum_eq = get_equity(date_str)

                    closed_trades_for_stats.append({
                        "ticker": pos.ticker, "entry_date": pos.entry_date,
                        "exit_date": date_str, "entry_price": pos.entry_price,
                        "exit_price": close, "shares": pos.initial_shares,
                        "pnl": pnl, "r_multiple": r_mult,
                        "holding_days": (pd.Timestamp(date_str) - pd.Timestamp(pos.entry_date)).days,
                        "exit_type": "structural_pure"
                    })

                    trades.append(make_trade_record(
                        date_str, pos.ticker, "SELL", pos.shares, close,
                        pnl, r_mult, cum_eq,
                        f"Pure ride structural exit: Close {close:.2f} < StopLine {stop_line:.2f}"
                    ))
                    recent_rs.append(r_mult)
                    positions_to_remove.append(pos)
                    continue

            # ── E3: Championship (Pure Ride + Hard Stop + ATR Sizing) ──
            elif pos.exit_system == "E3":
                hard_stop_price = pos.entry_price * (1 - HARD_STOP_PCT)

                # Priority 1: Hard max loss stop (intraday) — NEVER let a trade exceed 8% loss
                if low <= hard_stop_price:
                    open_price = float(row['Open'])
                    # If gapped below hard stop, take the open; otherwise take the hard stop level
                    exit_price = min(open_price, hard_stop_price) if open_price <= hard_stop_price else hard_stop_price
                    pnl = pos.shares * (exit_price - pos.entry_price)
                    r_mult = (exit_price - pos.entry_price) / pos.R if pos.R > 0 else 0
                    cash += pos.shares * exit_price
                    cum_eq = get_equity(date_str)

                    closed_trades_for_stats.append({
                        "ticker": pos.ticker, "entry_date": pos.entry_date,
                        "exit_date": date_str, "entry_price": pos.entry_price,
                        "exit_price": exit_price, "shares": pos.initial_shares,
                        "pnl": pnl, "r_multiple": r_mult,
                        "holding_days": (pd.Timestamp(date_str) - pd.Timestamp(pos.entry_date)).days,
                        "exit_type": "hard_stop"
                    })

                    trades.append(make_trade_record(
                        date_str, pos.ticker, "STOP", pos.shares, exit_price,
                        pnl, r_mult, cum_eq,
                        f"Hard stop hit: Low {low:.2f} <= {HARD_STOP_PCT*100:.0f}% stop at {hard_stop_price:.2f}"
                    ))
                    recent_rs.append(r_mult)
                    positions_to_remove.append(pos)
                    continue

                # Priority 2: Structural exit (same as Pure Ride): Close < StopLine
                elif close < stop_line:
                    pnl = pos.shares * (close - pos.entry_price)
                    r_mult = (close - pos.entry_price) / pos.R if pos.R > 0 else 0
                    cash += pos.shares * close
                    cum_eq = get_equity(date_str)

                    closed_trades_for_stats.append({
                        "ticker": pos.ticker, "entry_date": pos.entry_date,
                        "exit_date": date_str, "entry_price": pos.entry_price,
                        "exit_price": close, "shares": pos.initial_shares,
                        "pnl": pnl, "r_multiple": r_mult,
                        "holding_days": (pd.Timestamp(date_str) - pd.Timestamp(pos.entry_date)).days,
                        "exit_type": "structural_championship"
                    })

                    trades.append(make_trade_record(
                        date_str, pos.ticker, "SELL", pos.shares, close,
                        pnl, r_mult, cum_eq,
                        f"Championship structural exit: Close {close:.2f} < StopLine {stop_line:.2f}"
                    ))
                    recent_rs.append(r_mult)
                    positions_to_remove.append(pos)
                    continue

        # Remove closed positions
        for pos in positions_to_remove:
            if pos in positions:
                positions.remove(pos)

        # ── Step 4: Generate Entry Signals (for execution on T+1) ──
        open_slots = MAX_POSITIONS - len(positions) - len(pending_entries)
        if gate_on and open_slots > 0:
            held_tickers = {p.ticker for p in positions}
            pending_tickers = {e['ticker'] for e in pending_entries}

            # Retrieve pre-computed candidates for today in O(1) time
            day_signals = signals_by_date.get(date_str, [])
            valid_candidates = []

            for cand in day_signals:
                ticker = cand['ticker']
                if ticker in held_tickers or ticker in pending_tickers:
                    continue

                # RS mode verification
                if rs_mode == "ibd":
                    if cand['rs_ibd'] < RS_THRESHOLD: continue
                    rs_str = f"IBD RS={cand['rs_ibd']:.0f}"
                    rs_val = cand['rs_ibd']
                else:
                    if cand['rs_1m'] < RS_THRESHOLD: continue
                    rs_str = f"1M RS pctile={cand['rs_1m']:.0f}"
                    rs_val = cand['rs_1m']

                # Enforce Setup Filter
                if variant_filter == "modern_breakout" and not cand["is_m_breakout"]: continue
                if variant_filter == "modern_pullback" and not cand["is_m_pullback"]: continue
                if variant_filter == "modern_ep" and not cand["is_ep"]: continue
                if variant_filter is None and not cand["is_standard"]: continue

                gate_label = f"QQQ>{gate_sma}SMA"
                ema_high = cand.get('ema_high_8', 0)
                pb_pct = ((cand['close'] / ema_high) - 1) * 100 if ema_high else 0.0
                
                # Get ATH proximity data
                pct_from_52w = cand.get('pct_from_52w_high', -100.0)
                
                # Build reason string based on ranking method
                if rank_by == "ath":
                    reason = (
                        f"Entry: {rs_str}, {pct_from_52w:.1f}% from 52W high (ATH priority), "
                        f"bullish 8EMA structure, pullback {pb_pct:.1f}% from EMA cluster; "
                        f"{gate_label} gate ON"
                    )
                else:
                    reason = (
                        f"Entry: {rs_str}, bullish 8EMA structure, "
                        f"pullback {pb_pct:.1f}% from EMA cluster; "
                        f"{gate_label} gate ON"
                    )

                valid_candidates.append({
                    "ticker": ticker,
                    "initial_stop": cand['initial_stop'],
                    "rs_val": rs_val,
                    "pct_from_52w_high": pct_from_52w,
                    "reason": reason
                })

            # Sort by ranking method: ATH-proximity (closest to high) or RS (highest)
            if rank_by == "ath":
                # Primary: closest to 52W high (highest pct_from_52w_high, which is negative)
                # Secondary: highest RS as tiebreaker
                valid_candidates.sort(key=lambda c: (-c['pct_from_52w_high'], -c['rs_val']))
            else:
                # Original: sort by RS (highest first)
                valid_candidates.sort(key=lambda c: c['rs_val'], reverse=True)
            
            for vc in valid_candidates[:open_slots]:
                pending_entries.append(vc)

        # ── Step 5: Record Daily Equity ──
        total_equity = get_equity(date_str)
        invested = total_equity - cash
        equity_curve.append({
            "date": date_str,
            "equity": round(total_equity, 2),
            "cash": round(cash, 2),
            "invested": round(invested, 2),
            "positions_count": len(positions),
            "gate_on": gate_on
        })

    # ── Build Open Positions Snapshot ──
    open_positions = []
    last_date = trading_dates[-1] if trading_dates else None
    for pos in positions:
        last_row = get_ticker_row(pos.ticker, last_date) if last_date else None
        last_close = float(last_row['Close']) if last_row is not None else pos.entry_price
        stop_line = float(last_row['StopLine']) if last_row is not None and pd.notna(last_row.get('StopLine')) else pos.initial_stop
        unrealized = pos.shares * (last_close - pos.entry_price)
        dist_to_stop = ((last_close - stop_line) / last_close * 100) if last_close > 0 else 0

        open_positions.append({
            "ticker": pos.ticker,
            "qty": pos.shares,
            "entry_date": pos.entry_date,
            "avg_entry": round(pos.entry_price, 2),
            "last_close": round(last_close, 2),
            "unrealized_pnl": round(unrealized, 2),
            "unrealized_pnl_pct": round(unrealized / (pos.shares * pos.entry_price) * 100, 2) if pos.entry_price > 0 and pos.shares > 0 else 0,
            "current_stop_line": round(stop_line, 2),
            "distance_to_stop_pct": round(dist_to_stop, 2),
            "R": round(pos.R, 2),
            "has_scaled": pos.has_scaled,
            "reason": pos.reason
        })

    # ── Compute Metrics ──
    metrics = compute_metrics(equity_curve, closed_trades_for_stats, trades)

    # Record last gate status
    last_gate = gate_history[-1] if gate_history else {"gate_on": False}

    return {
        "variant_id": variant_id,
        "variant_label": variant_label,
        "config": {
            "gate_sma": gate_sma,
            "rs_mode": rs_mode,
            "exit_system": exit_system,
            "rank_by": rank_by,
            "starting_capital": STARTING_CAPITAL,
            "max_positions": MAX_POSITIONS,
            "sim_start_date": SIM_START_DATE,
            "rs_threshold": RS_THRESHOLD,
            "min_price": MIN_PRICE,
            "min_avg_dollar_vol": MIN_AVG_DOLLAR_VOL,
            "pullback_pct": PULLBACK_PCT
        },
        "trades": trades,
        "equity_curve": equity_curve,
        "open_positions": open_positions,
        "cash": round(cash, 2),
        "gate_status": last_gate,
        "metrics": metrics,
        "gate_history": gate_history,
        "data_through": trading_dates[-1] if trading_dates else None,
        "version": VERSION
    }


# ──────────────────────────────────────────────────────────────────
# Metrics Computation (Champion-Grade)
# ──────────────────────────────────────────────────────────────────
def compute_metrics(equity_curve: List[dict], closed_trades: List[dict],
                    all_trade_records: List[dict]) -> dict:
    """Compute champion-grade trading statistics."""
    metrics: Dict[str, Any] = {}

    # ── Performance ──
    if equity_curve:
        start_equity = STARTING_CAPITAL
        end_equity = equity_curve[-1]['equity']
        total_return = (end_equity - start_equity) / start_equity * 100

        # CAGR
        first_date = pd.Timestamp(equity_curve[0]['date'])
        last_date = pd.Timestamp(equity_curve[-1]['date'])
        days = (last_date - first_date).days
        years = days / 365.25 if days > 0 else 1
        cagr = ((end_equity / start_equity) ** (1 / years) - 1) * 100 if years > 0 and start_equity > 0 else 0

        # Max drawdown
        peak = start_equity
        max_dd = 0
        max_dd_pct = 0
        for pt in equity_curve:
            eq = pt['equity']
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            if dd > max_dd_pct:
                max_dd_pct = dd
                max_dd = peak - eq

        metrics['total_return_pct'] = round(total_return, 2)
        metrics['ending_equity'] = round(end_equity, 2)
        metrics['cagr_pct'] = round(cagr, 2)
        metrics['max_drawdown_pct'] = round(max_dd_pct, 2)
        metrics['max_drawdown_dollar'] = round(max_dd, 2)
    else:
        metrics['total_return_pct'] = 0
        metrics['ending_equity'] = STARTING_CAPITAL
        metrics['cagr_pct'] = 0
        metrics['max_drawdown_pct'] = 0
        metrics['max_drawdown_dollar'] = 0

    # ── Trade Statistics ──
    if closed_trades:
        wins = [t for t in closed_trades if t['pnl'] > 0]
        losses = [t for t in closed_trades if t['pnl'] <= 0]

        total_trades = len(closed_trades)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

        avg_win = sum(t['pnl'] for t in wins) / win_count if win_count > 0 else 0
        avg_loss = sum(t['pnl'] for t in losses) / loss_count if loss_count > 0 else 0
        payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

        avg_win_r = sum(t['r_multiple'] for t in wins) / win_count if win_count > 0 else 0
        avg_loss_r = sum(t['r_multiple'] for t in losses) / loss_count if loss_count > 0 else 0

        # Expectancy per trade
        expectancy_dollar = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)
        expectancy_r = (win_rate / 100 * avg_win_r) + ((1 - win_rate / 100) * avg_loss_r)

        # Profit factor
        gross_wins = sum(t['pnl'] for t in wins)
        gross_losses = abs(sum(t['pnl'] for t in losses))
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else float('inf')

        # Best / worst
        best_trade_r = max(t['r_multiple'] for t in closed_trades) if closed_trades else 0
        worst_trade_r = min(t['r_multiple'] for t in closed_trades) if closed_trades else 0
        best_trade_dollar = max(t['pnl'] for t in closed_trades) if closed_trades else 0
        worst_trade_dollar = min(t['pnl'] for t in closed_trades) if closed_trades else 0

        # Avg holding period
        avg_holding = sum(t['holding_days'] for t in closed_trades) / total_trades if total_trades > 0 else 0

        # Partial exits count
        partial_count = sum(1 for t in all_trade_records if t['action'] == 'PARTIAL')

        metrics['total_trades'] = total_trades
        metrics['win_count'] = win_count
        metrics['loss_count'] = loss_count
        metrics['win_rate_pct'] = round(win_rate, 1)
        metrics['avg_win_dollar'] = round(avg_win, 2)
        metrics['avg_loss_dollar'] = round(avg_loss, 2)
        metrics['avg_win_r'] = round(avg_win_r, 2)
        metrics['avg_loss_r'] = round(avg_loss_r, 2)
        metrics['payoff_ratio'] = round(payoff_ratio, 2) if payoff_ratio != float('inf') else 999.0
        metrics['expectancy_dollar'] = round(expectancy_dollar, 2)
        metrics['expectancy_r'] = round(expectancy_r, 4)
        metrics['profit_factor'] = round(profit_factor, 2) if profit_factor != float('inf') else 999.0
        metrics['best_trade_r'] = round(best_trade_r, 2)
        metrics['worst_trade_r'] = round(worst_trade_r, 2)
        metrics['best_trade_dollar'] = round(best_trade_dollar, 2)
        metrics['worst_trade_dollar'] = round(worst_trade_dollar, 2)
        metrics['avg_holding_days'] = round(avg_holding, 1)
        metrics['partial_exit_count'] = partial_count

        # ── Streaks ──
        streak_wins = 0
        streak_losses = 0
        max_streak_wins = 0
        max_streak_losses = 0
        current_streak_type = None
        current_streak = 0

        for t in closed_trades:
            if t['pnl'] > 0:
                if current_streak_type == 'win':
                    current_streak += 1
                else:
                    current_streak_type = 'win'
                    current_streak = 1
                max_streak_wins = max(max_streak_wins, current_streak)
            else:
                if current_streak_type == 'loss':
                    current_streak += 1
                else:
                    current_streak_type = 'loss'
                    current_streak = 1
                max_streak_losses = max(max_streak_losses, current_streak)

        metrics['max_consecutive_wins'] = max_streak_wins
        metrics['max_consecutive_losses'] = max_streak_losses
    else:
        metrics['total_trades'] = 0
        metrics['win_count'] = 0
        metrics['loss_count'] = 0
        metrics['win_rate_pct'] = 0
        metrics['avg_win_dollar'] = 0
        metrics['avg_loss_dollar'] = 0
        metrics['avg_win_r'] = 0
        metrics['avg_loss_r'] = 0
        metrics['payoff_ratio'] = 0
        metrics['expectancy_dollar'] = 0
        metrics['expectancy_r'] = 0
        metrics['profit_factor'] = 0
        metrics['best_trade_r'] = 0
        metrics['worst_trade_r'] = 0
        metrics['best_trade_dollar'] = 0
        metrics['worst_trade_dollar'] = 0
        metrics['avg_holding_days'] = 0
        metrics['partial_exit_count'] = 0
        metrics['max_consecutive_wins'] = 0
        metrics['max_consecutive_losses'] = 0

    # ── Exposure ──
    if equity_curve:
        days_with_pos = sum(1 for pt in equity_curve if pt['positions_count'] > 0)
        total_days = len(equity_curve)
        avg_exposure = sum(
            pt['invested'] / pt['equity'] * 100 if pt['equity'] > 0 else 0
            for pt in equity_curve
        ) / total_days if total_days > 0 else 0

        metrics['avg_exposure_pct'] = round(avg_exposure, 1)
        metrics['days_in_market'] = days_with_pos
        metrics['total_trading_days'] = total_days
        metrics['time_in_market_pct'] = round(days_with_pos / total_days * 100, 1) if total_days > 0 else 0
    else:
        metrics['avg_exposure_pct'] = 0
        metrics['days_in_market'] = 0
        metrics['total_trading_days'] = 0
        metrics['time_in_market_pct'] = 0
    # ── Yearly Returns ──
    yearly_returns = {}
    if equity_curve:
        by_year = {}
        for pt in equity_curve:
            year = pt['date'][:4]
            if year not in by_year:
                by_year[year] = []
            by_year[year].append(pt['equity'])
        
        for y, eq_list in by_year.items():
            if len(eq_list) > 0:
                y_start = eq_list[0]
                y_end = eq_list[-1]
                y_ret = ((y_end - y_start) / y_start * 100) if y_start > 0 else 0
                yearly_returns[y] = round(y_ret, 2)
    
    metrics['returns_by_year'] = yearly_returns

    return metrics


# ──────────────────────────────────────────────────────────────────
# Dynamic Start Date Computation
# ──────────────────────────────────────────────────────────────────
def compute_dynamic_start_date(qqq_df: pd.DataFrame, lookback_years: int) -> str:
    """
    Compute the simulation start date dynamically based on available data
    and the requested lookback period.

    Ensures:
    1. At least 252 trading days of warm-up for IBD RS computation
    2. SMA_200 is valid (needs 200+ days of history before sim start)
    3. The start date is at most `lookback_years` before the latest data date
    """
    all_dates = sorted(qqq_df['Date'].unique())
    latest_date = pd.Timestamp(all_dates[-1])
    earliest_date = pd.Timestamp(all_dates[0])

    # Target start = latest_date - lookback_years
    target_start = latest_date - pd.DateOffset(years=lookback_years)

    # We need at least 252 trading days of data BEFORE the sim start
    # for IBD RS warm-up (252d lookback) and SMA_200 (200d lookback)
    WARM_UP_DAYS = 252
    if len(all_dates) <= WARM_UP_DAYS:
        # Not enough data even for warm-up — use whatever we have
        # Start after the warm-up period
        if len(all_dates) > 50:  # At least use data after 50-day SMA is valid
            sim_start = all_dates[50]
        else:
            sim_start = all_dates[0]
        print(f"   ⚠️  Limited data ({len(all_dates)} days). Starting sim at {sim_start} with reduced warm-up.", flush=True)
        return sim_start

    # Find the index of the date closest to our target  
    warm_up_end_date = pd.Timestamp(all_dates[WARM_UP_DAYS])

    # Sim start must be AFTER the warm-up period
    effective_start = max(target_start, warm_up_end_date)

    # Find the actual closest trading date >= effective_start
    sim_start = None
    for d in all_dates:
        if pd.Timestamp(d) >= effective_start:
            sim_start = d
            break

    if sim_start is None:
        sim_start = all_dates[WARM_UP_DAYS]

    total_available = (latest_date - earliest_date).days / 365.25
    sim_span = (latest_date - pd.Timestamp(sim_start)).days / 365.25
    print(f"   📅 Dynamic start date: {sim_start} (data spans {total_available:.1f}y, sim spans {sim_span:.1f}y, warm-up: {WARM_UP_DAYS}d)", flush=True)

    return sim_start


# ──────────────────────────────────────────────────────────────────
# Main Entry Point
# ──────────────────────────────────────────────────────────────────
def run_all_variants(in_memory_data: Dict[str, pd.DataFrame] = None, lookback_years: int = None, **kwargs) -> List[dict]:
    """
    Main entry point. Loads OHLCV data once, precomputes indicators and
    rolling RS percentiles (lookahead-free), then runs all 16 variants.
    Pass in_memory_data to run directly from RAM (bypasses DB).
    
    Args:
        in_memory_data: Dict of ticker -> DataFrame (bypasses DB load)
        lookback_years: Simulation lookback period in years (default: SIM_LOOKBACK_YEARS env var or 5)
    """
    if lookback_years is None:
        lookback_years = SIM_LOOKBACK_YEARS

    start_time = time.time()

    print(f"📊 Portfolio Engine v{VERSION}: Loading data (lookback={lookback_years}y)...", flush=True)
    if in_memory_data is not None:
        all_data = {t: df.copy() for t, df in in_memory_data.items()}
    else:
        all_data = load_ohlcv_data()
    print(f"   Loaded {len(all_data)} tickers with OHLCV data", flush=True)

    if 'QQQ' not in all_data:
        print("   ⚠️  QQQ not found in data — cannot run simulation", flush=True)
        return []

    if 'SPY' not in all_data:
        print("   ⚠️  SPY not found in data — cannot compute RS", flush=True)
        return []

    # Compute indicators for all tickers
    print("📊 Portfolio Engine: Computing indicators...", flush=True)
    for ticker in list(all_data.keys()):
        all_data[ticker] = compute_indicators(all_data[ticker])

    # Compute ROLLING RS percentiles (both 1M and IBD) — NO lookahead bias
    print("📊 Portfolio Engine: Computing rolling RS percentiles (1M + IBD)...", flush=True)
    spy_df = all_data['SPY']
    all_data = compute_rolling_rs_percentiles(all_data, spy_df)

    # Convert all DataFrames to string-indexed Date for O(1) lookups
    for ticker in list(all_data.keys()):
        df = all_data[ticker]
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        df = df.set_index('Date', drop=False)
        all_data[ticker] = df

    # Get QQQ DataFrame with indicators
    qqq_df = all_data['QQQ']

    # Dynamically compute sim start date based on available data
    dynamic_start = compute_dynamic_start_date(qqq_df, lookback_years)

    # Build trading dates list (from QQQ as the master calendar)
    qqq_dates = qqq_df[qqq_df['Date'] >= dynamic_start]['Date']
    trading_dates = sorted(qqq_dates.tolist())

    if not trading_dates:
        print("   ⚠️  No trading dates found after computed start date", flush=True)
        return []

    sim_years = (pd.Timestamp(trading_dates[-1]) - pd.Timestamp(trading_dates[0])).days / 365.25
    print(f"   Simulation window: {trading_dates[0]} to {trading_dates[-1]} ({len(trading_dates)} days, {sim_years:.1f} years)", flush=True)

    # Data quality warnings
    warnings = []
    if sim_years < 1.0:
        warnings.append(f"Very short simulation period ({sim_years:.1f} years). Results may not be statistically significant.")
    if len(all_data) < 100:
        warnings.append(f"Small universe ({len(all_data)} tickers). RS rankings may be less meaningful.")
    if sim_years < lookback_years * 0.8:
        warnings.append(f"Requested {lookback_years}Y lookback but only {sim_years:.1f}Y of data available.")
    for w in warnings:
        print(f"   ⚠️  {w}", flush=True)

    # Precompute all possible entry signals using vectorized logic (lookahead-free)
    signals_by_date = precompute_signals(all_data)

    # Run each variant
    results = []
    for variant in VARIANTS:
        print(f"   Running variant {variant['id']}: {variant['label']}...", flush=True)
        result = run_variant(variant, all_data, qqq_df, signals_by_date, trading_dates)
        # Attach simulation metadata
        result['sim_period'] = {
            'start_date': trading_dates[0],
            'end_date': trading_dates[-1],
            'trading_days': len(trading_dates),
            'years': round(sim_years, 2),
            'lookback_years_requested': lookback_years,
            'universe_size': len(all_data),
            'warnings': warnings
        }
        results.append(result)
        t_count = result['metrics'].get('total_trades', 0)
        ret = result['metrics'].get('total_return_pct', 0)
        cagr = result['metrics'].get('cagr_pct', 0)
        pf = result['metrics'].get('profit_factor', 0)
        print(f"   ✅ {variant['id']}: {t_count} trades, {ret:+.1f}% total, {cagr:.1f}% CAGR, PF {pf:.2f}", flush=True)

    elapsed = time.time() - start_time
    print(f"📊 Portfolio Engine: All {len(results)} variants complete in {elapsed:.1f} seconds!", flush=True)
    return results


def store_results(results: List[dict]):
    """Store simulation results in the database."""
    with get_db() as conn:
        is_pg = hasattr(conn, 'info') or hasattr(conn, 'dsn')
        cursor = conn.cursor()

        # Clear all existing portfolio results to avoid stale data
        print("   🗑️  Clearing old portfolio results...", flush=True)
        cursor.execute("DELETE FROM portfolio_results")
        
        now = datetime.datetime.utcnow().isoformat()

        for result in results:
            variant_id = result['variant_id']
            result_json = json.dumps(result, default=str)
            data_through = result.get('data_through', '')

            if is_pg:
                cursor.execute("""
                    INSERT INTO portfolio_results (variant_id, result_json, computed_at, data_through, version)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (variant_id) DO UPDATE SET
                        result_json = EXCLUDED.result_json,
                        computed_at = EXCLUDED.computed_at,
                        data_through = EXCLUDED.data_through,
                        version = EXCLUDED.version
                """, (variant_id, result_json, now, data_through, VERSION))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO portfolio_results (variant_id, result_json, computed_at, data_through, version)
                    VALUES (?, ?, ?, ?, ?)
                """, (variant_id, result_json, now, data_through, VERSION))

        conn.commit()
    print(f"💾 Stored {len(results)} variant results in database", flush=True)
