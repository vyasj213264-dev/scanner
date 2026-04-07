# Portfolio Engine Enhancement: ATH-Proximity Ranking

## Summary

Enhanced the portfolio simulation engine to support **16 total strategy variants** (previously 8), adding a new entry allocation method that prioritizes stocks closest to their 52-week high.

## Changes Made

### 1. New Ranking Method: ATH-Proximity

**Original 8 Variants (RS-ranked):**
- Entry selection: Highest RS (Relative Strength) gets priority
- When multiple stocks meet RS ≥ 97 criteria, select those with highest RS values

**New 8 Variants (ATH-proximity ranked):**
- Entry selection: Closest to 52-week high gets priority, RS as tiebreaker
- When multiple stocks meet RS ≥ 97 criteria, select those closest to their 52W_High
- If multiple stocks have same distance from 52W high, highest RS wins

### 2. Implementation Details

#### Sorting Logic

**RS-Ranked (Original):**
```python
valid_candidates.sort(key=lambda c: c['rs_val'], reverse=True)
```

**ATH-Proximity Ranked (New):**
```python
# Primary: closest to 52W high (highest pct_from_52w_high, which is negative)
# Secondary: highest RS as tiebreaker
valid_candidates.sort(key=lambda c: (-c['pct_from_52w_high'], -c['rs_val']))
```

#### Example Ranking Comparison

Given these candidates:
- AAPL: -5% from 52W high, RS=98
- MSFT: -2% from 52W high, RS=97
- GOOGL: -2% from 52W high, RS=99
- NVDA: -10% from 52W high, RS=99

**RS Priority Ranking:**
1. GOOGL (RS=99)
2. NVDA (RS=99)
3. AAPL (RS=98)
4. MSFT (RS=97)

**ATH Priority Ranking:**
1. GOOGL (-2% from high, RS=99) ← Closest to ATH + highest RS
2. MSFT (-2% from high, RS=97) ← Closest to ATH
3. AAPL (-5% from high, RS=98)
4. NVDA (-10% from high, RS=99)

### 3. New Variant IDs

All new variants have `_ATH` suffix:

| Original Variant | New ATH Variant |
|-----------------|-----------------|
| G1_R1_E1 | G1_R1_E1_ATH |
| G1_R1_E2 | G1_R1_E2_ATH |
| G1_R2_E1 | G1_R2_E1_ATH |
| G1_R2_E2 | G1_R2_E2_ATH |
| G1_R2_E1_MB | G1_R2_E1_MB_ATH |
| G1_R2_E1_MP | G1_R2_E1_MP_ATH |
| G1_R2_E1_EP | G1_R2_E1_EP_ATH |
| G1_R2_E2_EP | G1_R2_E2_EP_ATH |

### 4. Data Flow

1. **Indicator Calculation** (`compute_indicators`):
   - Already calculates `52W_High` and `Pct_From_52W_High`
   - No changes needed

2. **Signal Precomputation** (`precompute_signals`):
   - Now includes `pct_from_52w_high` in each signal candidate
   - Default value: -100.0 if not available

3. **Entry Selection** (`run_variant`):
   - Reads `rank_by` parameter from variant config
   - Applies appropriate sorting based on `rank_by` value ("rs" or "ath")
   - Generates descriptive reason strings showing ATH distance

4. **Result Storage**:
   - Config now includes `rank_by` field
   - Trade records show ATH distance in reason string for ATH variants

### 5. Files Modified

- `api/services/portfolio_engine.py`:
  - Updated VARIANTS array (8 → 16)
  - Added `rank_by` parameter to variant configs
  - Enhanced `precompute_signals()` to include ATH data
  - Updated `run_variant()` to support both ranking methods
  - Updated documentation strings

- `api/routers/portfolio.py`:
  - Updated API documentation (8 → 16 variants)

## Testing

To verify the implementation:

1. Run the portfolio simulation:
   ```bash
   # This will compute all 16 variants
   POST /api/portfolio/simulate
   ```

2. Compare results between RS and ATH variants:
   ```bash
   # Original RS-ranked
   GET /api/portfolio/G1_R2_E2
   
   # New ATH-proximity ranked
   GET /api/portfolio/G1_R2_E2_ATH
   ```

3. Check trade reasons in the results to see ATH distance information

## Expected Impact

**Hypothesis:** Stocks near their 52-week highs often have stronger momentum and institutional support, potentially leading to:
- Better win rates
- Larger average wins
- Improved risk-adjusted returns

**Comparison:** The 16-variant system allows direct A/B testing of RS-ranked vs ATH-proximity ranked entry selection across all strategy configurations.

## Configuration

Each variant now includes a `rank_by` field in its config:

```json
{
  "variant_id": "G1_R2_E2_ATH",
  "config": {
    "gate_sma": 21,
    "rs_mode": "1m",
    "exit_system": "E2",
    "rank_by": "ath",
    ...
  }
}
```

## Backward Compatibility

- Original 8 variants unchanged (default `rank_by: "rs"`)
- Existing API endpoints work with all 16 variants
- Database schema unchanged (stores all variants in same table)
