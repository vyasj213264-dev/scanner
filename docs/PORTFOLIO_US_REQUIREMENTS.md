# US Portfolio Simulator — End-to-End Requirements

**Document status:** Draft for implementation  
**Market scope:** United States (US) only for v1  
**Related product goal:** A dedicated **Portfolio** experience that combines (a) **historical simulation** from an agreed start date, (b) **live “as of today”** portfolio state, and (c) **champion-grade trading statistics**—in the spirit of **Dan Zanger** (momentum/trend) and **Nicolas Darvas** (structured trend following), without claiming to replicate any individual’s private process.

---

## 1. Purpose

Deliver a **rules-based portfolio engine** and **UI** that:

1. Runs **eight parallel strategy variants** (see §5) on **daily** data.
2. Produces a **complete audit trail**: every buy, scale, stop, exit; portfolio value over time; open positions; cash.
3. Surfaces **investing-champion style metrics** (win rate, payoff, expectancy, streaks, drawdown, R-multiples, etc.).
4. Shows **current / today** portfolio composition and marks (see §11).

This is a **simulation / research / discipline tool**, not personalized investment advice.

---

## 2. Definitions

| Term | Meaning in this document |
|------|---------------------------|
| **DMA** | Daily **simple moving average** of **close**, unless explicitly stated otherwise (e.g. “EMA”). *If product prefers EMA for QQQ gate, state in build notes and keep consistent.* |
| **8 EMA triple structure** | On each daily bar: `MAHigh = EMA(high, 8)`, `MAClose = EMA(close, 8)`, `MALow = EMA(low, 8)` (Pine Script2-style). |
| **8 EMA low (stop line)** | `StopLine = EMA(low, 8)` on the daily series. |
| **Bullish structure bar** | `Close > MAHigh AND Close > MAClose AND Close > MALow`. |
| **Bearish structure break (for exits)** | **End-of-day** `Close < StopLine` (i.e. close below **8 EMA of lows**). |
| **R (risk unit)** | Initial risk per share = `EntryPrice - InitialStopPrice` (must be > 0). |
| **3R profit** | Unrealized profit ≥ **3 × R** per **remaining** share (implementation must define measurement timing: close vs intraday—default **daily close** for v1). |
| **IBD-style RS** | The application’s existing **`RS_Rating`** field (cross-sectional percentile rank derived from stored methodology—see ingest). Threshold for eligibility: **`RS_Rating ≥ 97`**. |
| **1M RS (vs SPY)** | For each symbol and date: compute **21 trading day** total return ratio vs **SPY** over the same window: \((1+r_{stock})/(1+r_{SPY})\) or simple outperformance ratio—**pick one formula in implementation** and keep constant. Then convert to a **percentile rank across the US tradable universe** for that date. Eligibility threshold: **≥ 97th percentile** (mirror the IBD numeric cutoff for comparability). |

---

## 3. Scope

### 3.1 In scope (v1)

- US market only.
- **Daily** bar logic only (no intraday unless explicitly added later).
- **Eight** strategy variants (§5).
- Starting capital **$100,000** (configurable constant).
- Max **4** positions; **~25% of current equity** per **new** position (equal-weight intent across open slots—see §6).
- Historical window: **from 2025-01-01** (configurable) through last available ingest date.
- **No slippage, no commissions** in v1 (explicitly stated).

### 3.2 Out of scope (v1)

- Indian market portfolio variant.
- Short selling.
- Options, margin, borrow fees.
- Intraday stops (unless later phase).
- Tax reporting, broker execution, real money.

---

## 4. Strategy grid (eight portfolios)

Each portfolio is the combination of:

| Dimension | Values |
|-----------|--------|
| **QQQ trend gate** | (G1) `QQQ Close > QQQ 21-DMA` **or** (G2) `QQQ Close > QQQ 50-DMA` |
| **Relative strength mode** | (R1) **IBD-style** `RS_Rating ≥ 97` **or** (R2) **1M RS vs SPY** percentile **≥ 97** |
| **Exit system** | (E1) **Scale + breakeven + runner rules** **or** (E2) **Pure ride** until structure break |

**Total:** 2 × 2 × 2 = **8** named variants (labels are implementation detail).

### 4.1 QQQ gate behavior (default)

When the selected gate is **false** (QQQ not above the chosen DMA):

- **No new entries** are allowed.
- **Existing positions** remain open and are managed **only** by the position’s **exit system** (E1/E2) and structural stop rules—unless product explicitly chooses “force flat on regime flip” (not selected in current discussions).

*Requirement:* The UI must show **whether the gate was ON or OFF** on each day for the selected variant.

---

## 5. Entry rules (all variants)

### 5.1 Universe

- US symbols present in application data with sufficient history for indicators and RS.
- Liquidity filters **TBD minimum** (e.g. min price, min avg dollar volume); must be documented in implementation notes so backtests are reproducible.

### 5.2 Eligibility (RS)

On signal evaluation day **T**:

- **R1 (IBD-style):** `RS_Rating ≥ 97` as of **T** (or T−1 if using prior close—**pick one convention** and apply everywhere).
- **R2 (1M vs SPY percentile):** stock’s 1M relative strength percentile **≥ 97** as of **T** (same timing convention as R1).

### 5.3 Trend / pullback “structure” entry (8 EMA)

Minimum entry conditions (daily):

1. **Bullish structure** as defined in §2 (close above all three 8 EMA lines derived from high/close/low).
2. Stock must be in an **uptrend context** compatible with the strategy: **Close > 8 EMA low line** at entry (no longs already broken).
3. **Optional tightening (v1 default ON unless changed):** require **rising** triple structure for **K** consecutive days **or** require price to be **within X%** of a “pullback” to the 8 EMA cluster—**exact pullback rule TBD**; until tightened, “bullish structure bar” may be too permissive. *Implementation must log which sub-rule is used.*

### 5.4 Portfolio capacity

- Maximum **4** open positions.
- If fewer than 4 slots and a valid entry signal exists and **QQQ gate** is **true**, **allocate** per §6.

### 5.5 Entry price (default for simulation)

**Default:** enter at **next trading day’s open** after the signal bar (reduces look-ahead).  
**Alternative (optional flag):** enter at **signal close**.  
*Requirement:* One convention per build; document in release notes.

### 5.6 Initial stop (initial R)

- **InitialStopPrice = StopLine** on the **entry day** (8 EMA of lows), **or** previous bar’s StopLine—**pick one** and keep constant.
- If **EntryPrice ≤ InitialStopPrice**, **no trade** (invalid risk).

---

## 6. Position sizing

- **Starting equity:** $100,000.
- **Target weight:** each new position targets **~25% of current total equity** (cash + market value of open positions at **last close**).
- **Rounding:** round shares to whole shares; residual cash tracked.
- **Max positions:** 4.

---

## 7. Exit rules

### 7.1 Structural exit (applies to both E1 and E2)

**Full exit** when **daily close < StopLine** (8 EMA of lows), **unless** a more specific rule in E1 triggers first (e.g. breakeven fill—see below).

StopLine is **updated daily** after each close (standard EMA of lows series).

### 7.2 Exit system E2 — “Pure ride”

- **100%** of shares remain until **structural exit** (§7.1).
- No partials, no breakeven moves.

### 7.3 Exit system E1 — “Scale at 3R + breakeven runner”

1. **Define R** at entry from §5.6.
2. When **profit ≥ 3R** (on **full** position, measured at **daily close** by default):
   - Sell **1/3** of **shares** (rounded per implementation rules).
   - Move stop on **remaining** shares to **breakeven** = **entry price**.
3. **Runner exits** when **either** occurs first:
   - **Structural:** `Close < StopLine` (8 EMA low break), **or**
   - **Breakeven stop:** price trades through entry from above **(default fill model: if `Low ≤ EntryPrice`, exit remainder at `EntryPrice` that day)**.

*Note:* If both could occur same day, precedence must be deterministic (document: typically **check structural close vs BE intraday low ordering**).

---

## 8. Metrics & reporting (champion-style)

For **each** of the 8 variants, compute and display:

### 8.1 Performance

- CAGR (if window long enough), total return, ending equity.
- Max drawdown (peak-to-trough on equity curve).
- Monthly / weekly equity curve (minimum: daily equity time series).

### 8.2 Trade statistics

- Win rate (%).
- Average win / average loss (dollars and R).
- Payoff ratio (avg win / abs avg loss).
- Expectancy per trade (R and $).
- Profit factor (gross wins / gross losses).
- Best / worst trade (R and $).
- Average holding period (days).
- Trade count, # of full exits, # of partial exits.

### 8.3 Streaks

- Max consecutive wins / losses.

### 8.4 Exposure

- Average exposure (% invested).
- Time in market / number of days with ≥1 position.

---

## 9. UI requirements (Portfolio page)

### 9.1 Variant selection

- User selects **one** of **8** variants **or** compares **two** side-by-side (nice-to-have v1.1).

### 9.2 Historical (from 2025-01-01)

- **Trades table:** date, symbol, action (BUY, PARTIAL, SELL, STOP), qty, price, fees (0 in v1), P&L, **R-multiple**, cumulative equity, **reason string** (e.g. “Entry: RS≥97, bullish 8EMA structure; QQQ>50DMA gate ON”).
- **Event log** for non-trade events if needed (e.g. “Gate OFF: no new buys”).
- **Portfolio snapshots:** optional end-of-week holdings listing.

### 9.3 Live / today

- Open positions: symbol, qty, avg entry, **last close**, unrealized P&L, current StopLine, distance to stop.
- Cash balance.
- **Gate status** for selected QQQ rule as of last close.

### 9.4 Charts

- Equity curve.
- Underwater / drawdown chart (nice-to-have).

---

## 10. Data dependencies

- Daily OHLCV for US universe symbols.
- Daily OHLCV for **QQQ** and **SPY**.
- Existing **`RS_Rating`** pipeline for R1 mode.
- Computed **1M vs SPY** percentile series for R2 mode (derived in batch from price history).

---

## 11. Non-functional requirements

- **Reproducibility:** Same inputs → same outputs (deterministic rounding rules).
- **Performance:** Backtest may be precomputed nightly/weekly; UI reads stored results.
- **Auditability:** Each exported row links to rule version string (semver) embedded in output JSON.

---


## 12. Resolved implementation decisions (formerly open items)

All items below are **CLOSED** as of v0.2. These decisions are binding for the v1 implementation.

| # | Item | Resolution |
|---|------|------------|
| 1 | **QQQ / SPY moving averages** | **SMA (Simple Moving Average)** for ALL "DMA" labelled calculations throughout the system. This includes QQQ 21-DMA gate, QQQ 50-DMA gate, and any other DMA reference. Consistency is paramount. |
| 2 | **Entry signal permissiveness** | Beyond the bullish structure bar, require a **physical pullback filter**: the stock's close must be **within 2% of the 8 EMA cluster** (specifically, `Close <= MAHigh * 1.02`). This prevents chasing extended moves and is inspired by Darvas/Zanger pullback discipline. |
| 3 | **RS timing** | **Prior close** convention. RS eligibility (`RS_Rating` or 1M RS percentile) is evaluated using the **end-of-day values from the signal bar** (day T). Entry is taken at **next trading day's open** (day T+1). This convention applies to ALL simulations for this functionality. |
| 4 | **1M RS formula** | Use **21 trading days** as the 1-month lookback. Formula: `(Close_stock_T / Close_stock_T-21) / (Close_SPY_T / Close_SPY_T-21)`. Then rank across the full US tradable universe to get percentile. Threshold: **>= 97th percentile**. |
| 5 | **Minimum liquidity** | Dan Zanger / Darvas-inspired liquidity filters: **Price >= $10**, **50-day average dollar volume >= $5M/day** (ensures institutional-grade liquidity). These are minimum thresholds for a stock to be eligible for entry in ANY variant. |
| 6 | **Concurrent same-day events** | **Structural close takes precedence**. On any day where both a breakeven stop (Low <= EntryPrice) and a structural break (Close < StopLine) could trigger, evaluate structural close first. If `Close < StopLine`, exit at close. Otherwise, if `Low <= EntryPrice`, exit at EntryPrice (breakeven). |

### Additional confirmed conventions

- **Entry price:** **Next trading day's open** after the signal bar (T+1 open). No signal-close entries in v1.
- **Initial stop (InitialStopPrice):** **Previous bar's StopLine** (8 EMA of lows on day T, the signal bar).
- **All moving averages labelled "DMA":** **SMA** (simple), applied consistently everywhere.

---

## 13. Acceptance criteria (v1)

1. All **8** variants produce **distinct** result objects (may overlap trades).
2. For a **golden test symbol window**, manual spot-check: **entry, 3R partial, BE exit, structural exit** paths behave as per section 7.
3. UI lists **all trades** from **2025-01-01** with **no missing** exit rows for closed positions.
4. **Live** section matches **last close** reconstruction for "today."

---

## 14. Revision history

| Version | Date | Author | Notes |
|---------|------|--------|--------|
| 0.1 | 2026-03-29 | Product / eng | Initial consolidated spec from discovery |
| 0.2 | 2026-04-05 | eng | Closed all open items. SMA everywhere, 2% pullback filter, prior-close RS timing, next-day-open entry, $10 min price / $5M avg dollar vol, previous bar StopLine, structural close precedence. |
