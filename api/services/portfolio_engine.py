"""
Portfolio Simulation Engine — US Market
========================================
Runs 8 parallel strategy variants on daily OHLCV data producing:
- Complete trade audit trail
- Daily equity curve
- Champion-grade trading statistics (Zanger / Darvas style)

All "DMA" = SMA (Simple Moving Average) — confirmed in spec v0.2.
Entry at T+1 Open after signal on T. InitialStop = previous bar's StopLine.

Version: 1.0.0
"""

import math
import json
import datetime
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

import pandas as pd
import numpy as np

from api.database import get_db

# ──────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────
STARTING_CAPITAL = 100_000.0
MAX_POSITIONS = 4
TARGET_WEIGHT = 0.25  # 25% of equity per position
SIM_START_DATE = "2025-01-01"
EMA_PERIOD = 8
RS_THRESHOLD = 97
MIN_PRICE = 10.0
MIN_AVG_DOLLAR_VOL = 5_000_000.0  # $5M/day
PULLBACK_PCT = 0.02  # 2% pullback filter
VERSION = "1.0.0"

# 8 Strategy Variant Definitions
VARIANTS = [
    {"id": "G1_R1_E1", "label": "QQQ>21SMA · IBD RS≥97 · Scale+BE",  "gate_sma": 21, "rs_mode": "ibd",  "exit": "E1"},
    {"id": "G1_R1_E2", "label": "QQQ>21SMA · IBD RS≥97 · Pure Ride", "gate_sma": 21, "rs_mode": "ibd",  "exit": "E2"},
    {"id": "G1_R2_E1", "label": "QQQ>21SMA · 1M RS≥97 · Scale+BE",   "gate_sma": 21, "rs_mode": "1m",   "exit": "E1"},
    {"id": "G1_R2_E2", "label": "QQQ>21SMA · 1M RS≥97 · Pure Ride",  "gate_sma": 21, "rs_mode": "1m",   "exit": "E2"},
    {"id": "G2_R1_E1", "label": "QQQ>50SMA · IBD RS≥97 · Scale+BE",  "gate_sma": 50, "rs_mode": "ibd",  "exit": "E1"},
    {"id": "G2_R1_E2", "label": "QQQ>50SMA · IBD RS≥97 · Pure Ride", "gate_sma": 50, "rs_mode": "ibd",  "exit": "E2"},
    {"id": "G2_R2_E1", "label": "QQQ>50SMA · 1M RS≥97 · Scale+BE",   "gate_sma": 50, "rs_mode": "1m",   "exit": "E1"},
    {"id": "G2_R2_E2", "label": "QQQ>50SMA · 1M RS≥97 · Pure Ride",  "gate_sma": 50, "rs_mode": "1m",   "exit": "E2"},
]


# ──────────────────────────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────────────────────────
def load_ohlcv_data() -> Dict[str, pd.DataFrame]:
    """Load all US daily OHLCV from database, return dict of ticker -> DataFrame."""
    with get_db() as conn:
        is_pg = hasattr(conn, 'info') or hasattr(conn, 'dsn')
        cursor = conn.cursor()

        query = """
            SELECT Ticker, Date, Open, High, Low, Close, Volume
            FROM daily_ohlcv
            WHERE Market = 'US'
            ORDER BY Ticker, Date ASC
        """
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

    # Group into per-ticker DataFrames
    ticker_data: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        ticker_data[r['Ticker'] if 'Ticker' in r else r['ticker']].append(r)

    result = {}
    for ticker, records in ticker_data.items():
        df = pd.DataFrame(records)
        # Normalize column names
        col_map = {c: c.capitalize() if c[0].islower() else c for c in df.columns}
        df = df.rename(columns=col_map)
        for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').reset_index(drop=True)
        df = df.dropna(subset=['Close'])
        if len(df) >= 30:  # Need minimum history for indicators
            result[ticker] = df

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

    return df


def compute_1m_rs_percentiles(all_data: Dict[str, pd.DataFrame], spy_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Compute 1-month (21 trading day) relative strength vs SPY for each ticker,
    then rank across the universe to produce daily percentiles.
    Returns dict of ticker -> DataFrame with '1M_RS_Pctile' column added.
    """
    # Build a date-aligned universe of 1M returns ratio vs SPY
    spy_dates = spy_df.set_index('Date')['Close']

    # Compute SPY 21d return for all dates
    spy_ret_21 = spy_dates / spy_dates.shift(21)

    # For each ticker, compute ratio
    ticker_ratios: Dict[str, pd.Series] = {}
    for ticker, df in all_data.items():
        if ticker in ('SPY', 'QQQ', 'IWM'):
            continue
        ts = df.set_index('Date')['Close']
        stock_ret_21 = ts / ts.shift(21)
        # Align with SPY
        ratio = stock_ret_21 / spy_ret_21.reindex(stock_ret_21.index)
        ratio = ratio.dropna()
        if len(ratio) > 0:
            ticker_ratios[ticker] = ratio

    if not ticker_ratios:
        return all_data

    # Build a combined DataFrame to compute cross-sectional percentiles per date
    combined = pd.DataFrame(ticker_ratios)
    # Percentile rank across tickers for each date (0-100 scale)
    percentiles = combined.rank(axis=1, pct=True) * 100

    # Merge back into each ticker's DataFrame
    for ticker, df in all_data.items():
        if ticker in percentiles.columns:
            pctile_series = percentiles[ticker]
            df = df.set_index('Date')
            df['1M_RS_Pctile'] = pctile_series
            df = df.reset_index()
            all_data[ticker] = df
        else:
            df['1M_RS_Pctile'] = np.nan

    return all_data


# ──────────────────────────────────────────────────────────────────
# Position & Trade Tracking
# ──────────────────────────────────────────────────────────────────
class Position:
    """Tracks a single open position."""
    __slots__ = [
        'ticker', 'entry_date', 'entry_price', 'shares', 'initial_shares',
        'initial_stop', 'R', 'has_scaled', 'stop_moved_to_be',
        'exit_system', 'reason'
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
                qqq_df: pd.DataFrame, ibd_rs: Dict[str, float],
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

    # Pre-compute QQQ gate series
    qqq_indexed = qqq_df.set_index('Date')
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

    def get_equity(date_str: str) -> float:
        """Calculate total equity = cash + sum of position market values."""
        total = cash
        for pos in positions:
            if pos.ticker in all_data:
                df = all_data[pos.ticker]
                day_row = df[df['Date'] == date_str]
                if not day_row.empty:
                    total += pos.shares * float(day_row.iloc[0]['Close'])
                else:
                    # Use entry price as fallback
                    total += pos.shares * pos.entry_price
            else:
                total += pos.shares * pos.entry_price
        return total

    def get_ticker_row(ticker: str, date_str: str) -> Optional[pd.Series]:
        """Get a ticker's data row for a specific date."""
        if ticker not in all_data:
            return None
        df = all_data[ticker]
        rows = df[df['Date'] == date_str]
        if rows.empty:
            return None
        return rows.iloc[0]

    for i, date_str in enumerate(trading_dates):

        # ── Step 1: Check QQQ Gate ──
        qqq_row = None
        if date_str in qqq_indexed.index:
            qqq_row = qqq_indexed.loc[date_str]
        gate_on = False
        if qqq_row is not None and pd.notna(qqq_row.get(sma_col)):
            gate_on = float(qqq_row['Close']) > float(qqq_row[sma_col])

        gate_history.append({
            "date": date_str,
            "gate_on": gate_on,
            "qqq_close": round(float(qqq_row['Close']), 2) if qqq_row is not None else None,
            "qqq_sma": round(float(qqq_row[sma_col]), 2) if qqq_row is not None and pd.notna(qqq_row.get(sma_col)) else None
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
            if entry_price <= initial_stop:
                # Invalid risk — skip
                events_log.append({"date": date_str, "event": f"Skipped {ticker}: entry {entry_price:.2f} <= stop {initial_stop:.2f}"})
                continue

            # Position sizing: 25% of current equity
            current_equity = get_equity(date_str)
            alloc = current_equity * TARGET_WEIGHT
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
                unrealized_per_share = close - pos.entry_price

                # Check if 3R reached and we haven't scaled yet
                if not pos.has_scaled and pos.R > 0 and unrealized_per_share >= 3 * pos.R:
                    # Sell 1/3 of shares
                    sell_shares = max(1, pos.initial_shares // 3)
                    sell_shares = min(sell_shares, pos.shares)
                    pnl = sell_shares * (close - pos.entry_price)
                    r_mult = unrealized_per_share / pos.R if pos.R > 0 else 0

                    pos.shares -= sell_shares
                    cash += sell_shares * close
                    pos.has_scaled = True
                    pos.stop_moved_to_be = True  # Move stop to breakeven

                    cum_eq = get_equity(date_str)
                    trades.append(make_trade_record(
                        date_str, pos.ticker, "PARTIAL", sell_shares, close,
                        pnl, r_mult, cum_eq,
                        f"3R profit reached ({unrealized_per_share / pos.R:.1f}R). Sold 1/3, stop moved to breakeven."
                    ))

                # After scaling, check exits with precedence: structural first
                if pos.has_scaled and pos.shares > 0:
                    # Structural exit: Close < StopLine
                    if close < stop_line:
                        pnl = pos.shares * (close - pos.entry_price)
                        r_mult = (close - pos.entry_price) / pos.R if pos.R > 0 else 0
                        cash += pos.shares * close
                        cum_eq = get_equity(date_str)
                        pnl_total = (pos.initial_shares - pos.shares) * 0 + pnl  # partial already booked

                        closed_trades_for_stats.append({
                            "ticker": pos.ticker, "entry_date": pos.entry_date,
                            "exit_date": date_str, "entry_price": pos.entry_price,
                            "exit_price": close, "shares": pos.initial_shares,
                            "pnl": pnl, "r_multiple": r_mult,
                            "holding_days": (pd.Timestamp(date_str) - pd.Timestamp(pos.entry_date)).days,
                            "exit_type": "structural_after_partial"
                        })

                        trades.append(make_trade_record(
                            date_str, pos.ticker, "SELL", pos.shares, close,
                            pnl, r_mult, cum_eq,
                            f"Structural exit: Close {close:.2f} < StopLine {stop_line:.2f}"
                        ))
                        positions_to_remove.append(pos)
                        continue

                    # Breakeven stop: Low <= EntryPrice (intraday)
                    elif pos.stop_moved_to_be and low <= pos.entry_price:
                        exit_price = pos.entry_price  # Fill at breakeven
                        pnl = pos.shares * (exit_price - pos.entry_price)  # ~0
                        r_mult = 0.0
                        cash += pos.shares * exit_price
                        cum_eq = get_equity(date_str)

                        closed_trades_for_stats.append({
                            "ticker": pos.ticker, "entry_date": pos.entry_date,
                            "exit_date": date_str, "entry_price": pos.entry_price,
                            "exit_price": exit_price, "shares": pos.initial_shares,
                            "pnl": pnl, "r_multiple": r_mult,
                            "holding_days": (pd.Timestamp(date_str) - pd.Timestamp(pos.entry_date)).days,
                            "exit_type": "breakeven_stop"
                        })

                        trades.append(make_trade_record(
                            date_str, pos.ticker, "STOP", pos.shares, exit_price,
                            pnl, r_mult, cum_eq,
                            f"Breakeven stop hit: Low {low:.2f} <= Entry {pos.entry_price:.2f}"
                        ))
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
                    positions_to_remove.append(pos)
                    continue

        # Remove closed positions
        for pos in positions_to_remove:
            if pos in positions:
                positions.remove(pos)

        # ── Step 4: Generate Entry Signals (for execution on T+1) ──
        open_slots = MAX_POSITIONS - len(positions) - len(pending_entries)
        if gate_on and open_slots > 0:
            # Find candidates
            held_tickers = {p.ticker for p in positions}
            pending_tickers = {e['ticker'] for e in pending_entries}

            candidates = []
            for ticker, df in all_data.items():
                if ticker in ('SPY', 'QQQ', 'IWM', 'DIA'):
                    continue
                if ticker in held_tickers or ticker in pending_tickers:
                    continue

                row = df[df['Date'] == date_str]
                if row.empty:
                    continue
                row = row.iloc[0]

                # Liquidity filter
                close_val = float(row['Close'])
                if close_val < MIN_PRICE:
                    continue
                avg_dv = row.get('Avg_Dollar_Vol_50')
                if pd.isna(avg_dv) or float(avg_dv) < MIN_AVG_DOLLAR_VOL:
                    continue

                # Bullish structure
                if not row.get('Bullish_Structure', False):
                    continue

                # Pullback filter
                if not row.get('Pullback_OK', False):
                    continue

                # Uptrend context: Close > StopLine
                stop_line = row.get('StopLine')
                if pd.isna(stop_line) or close_val <= float(stop_line):
                    continue

                # RS eligibility (prior close = today's end-of-day values)
                if rs_mode == "ibd":
                    rs_val = ibd_rs.get(ticker, 0)
                    if rs_val < RS_THRESHOLD:
                        continue
                    rs_str = f"IBD RS={rs_val:.0f}"
                elif rs_mode == "1m":
                    pctile = row.get('1M_RS_Pctile')
                    if pd.isna(pctile) or float(pctile) < RS_THRESHOLD:
                        continue
                    rs_str = f"1M RS pctile={float(pctile):.0f}"
                else:
                    continue

                # InitialStop = previous bar's StopLine (day T-1)
                signal_idx = df.index[df['Date'] == date_str]
                if len(signal_idx) == 0:
                    continue
                idx_pos = signal_idx[0]
                if idx_pos < 1:
                    continue
                # The signal bar is day T (today). InitialStop uses T-1's StopLine.
                prev_bar = df.iloc[idx_pos - 1]
                initial_stop = float(prev_bar['StopLine']) if pd.notna(prev_bar.get('StopLine')) else None

                if initial_stop is None or initial_stop <= 0:
                    continue

                gate_label = f"QQQ>{gate_sma}SMA"
                reason = (
                    f"Entry: {rs_str}, bullish 8EMA structure, "
                    f"pullback {((close_val / float(row['EMA_High_8'])) - 1) * 100:.1f}% from EMA cluster; "
                    f"{gate_label} gate ON"
                )

                candidates.append({
                    "ticker": ticker,
                    "close": close_val,
                    "initial_stop": initial_stop,
                    "rs_val": rs_val if rs_mode == "ibd" else float(pctile) if not pd.isna(pctile) else 0,
                    "reason": reason
                })

            # Sort by RS (highest first) and take top N to fill slots
            candidates.sort(key=lambda c: c['rs_val'], reverse=True)
            for cand in candidates[:open_slots]:
                pending_entries.append(cand)

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
            "unrealized_pnl_pct": round(unrealized / (pos.shares * pos.entry_price) * 100, 2) if pos.entry_price > 0 else 0,
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

    return metrics


# ──────────────────────────────────────────────────────────────────
# Main Entry Point
# ──────────────────────────────────────────────────────────────────
def run_all_variants() -> List[dict]:
    """
    Run all 8 strategy variants and return results.
    This is the main entry point called by the API.
    """
    print("📊 Portfolio Engine: Loading OHLCV data...", flush=True)
    all_data = load_ohlcv_data()
    print(f"   Loaded {len(all_data)} tickers with OHLCV data", flush=True)

    if 'QQQ' not in all_data:
        print("   ⚠️  QQQ not found in data — cannot run simulation", flush=True)
        return []

    if 'SPY' not in all_data:
        print("   ⚠️  SPY not found in data — cannot compute 1M RS", flush=True)
        return []

    # Compute indicators for all tickers
    print("📊 Portfolio Engine: Computing indicators...", flush=True)
    for ticker in all_data:
        all_data[ticker] = compute_indicators(all_data[ticker])

    # Compute 1M RS percentiles
    print("📊 Portfolio Engine: Computing 1M RS percentiles...", flush=True)
    spy_df = all_data['SPY']
    all_data = compute_1m_rs_percentiles(all_data, spy_df)

    # Load IBD-style RS ratings from screen_data
    print("📊 Portfolio Engine: Loading IBD RS ratings...", flush=True)
    ibd_rs = load_rs_ratings()
    print(f"   Loaded RS ratings for {len(ibd_rs)} tickers", flush=True)

    # Get QQQ DataFrame with indicators
    qqq_df = all_data['QQQ']

    # Build trading dates list (from QQQ as the master calendar)
    qqq_dates = qqq_df[qqq_df['Date'] >= pd.Timestamp(SIM_START_DATE)]['Date']
    trading_dates = [d.strftime('%Y-%m-%d') for d in sorted(qqq_dates)]

    if not trading_dates:
        print("   ⚠️  No trading dates found after SIM_START_DATE", flush=True)
        return []

    print(f"   Simulation window: {trading_dates[0]} to {trading_dates[-1]} ({len(trading_dates)} days)", flush=True)

    # Convert dates in all DataFrames to string for consistent lookup
    for ticker in all_data:
        all_data[ticker]['Date'] = all_data[ticker]['Date'].dt.strftime('%Y-%m-%d')

    # Re-acquire QQQ reference AFTER date conversion (previous ref is now stale)
    qqq_df = all_data['QQQ']

    # Run each variant
    results = []
    for variant in VARIANTS:
        print(f"   Running variant {variant['id']}: {variant['label']}...", flush=True)
        result = run_variant(variant, all_data, qqq_df, ibd_rs, trading_dates)
        results.append(result)
        t_count = result['metrics'].get('total_trades', 0)
        ret = result['metrics'].get('total_return_pct', 0)
        print(f"   ✅ {variant['id']}: {t_count} trades, {ret:+.1f}% return", flush=True)

    print(f"📊 Portfolio Engine: All {len(results)} variants complete!", flush=True)
    return results


def store_results(results: List[dict]):
    """Store simulation results in the database."""
    with get_db() as conn:
        is_pg = hasattr(conn, 'info') or hasattr(conn, 'dsn')
        cursor = conn.cursor()

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
