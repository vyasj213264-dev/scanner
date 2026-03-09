from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
import re
from collections import defaultdict
from api.database import get_db

router = APIRouter(prefix="/api/v1/chart", tags=["chart"])

@router.get("/{ticker:path}")
async def get_chart_data(ticker: str) -> List[Dict[str, Any]]:
    """
    Fetches the historical trailing 1-year OHLCV data for a ticker.
    Supports basic average formulas like (AAPL+MSFT+GOOG)/3 for proxy indexes.
    """
    try:
        with get_db() as db:
            is_postgres = hasattr(db, 'dsn') or (hasattr(db, 'info') and getattr(db, 'info', None) is not None)
            cursor = db.cursor()
            if not is_postgres:
                import sqlite3
                db.row_factory = sqlite3.Row
                cursor = db.cursor()

            # Check if it's a proxy formula: (TICKER1+TICKER2)/N
            formula_match = re.match(r'^\(((?:[A-Za-z0-9]+(?:\+[A-Za-z0-9]+)*))\)/(\d+)$', ticker)
            if formula_match:
                tickers = formula_match.group(1).split('+')
                divisor = int(formula_match.group(2))
            
                # Fetch data for all tickers
                placeholders = ', '.join(['%s' if is_postgres else '?'] * len(tickers))
                query = f"""
                    SELECT Ticker, Date as time, Open as open, High as high, Low as low, Close as close, Volume as volume
                    FROM daily_ohlcv
                    WHERE Ticker IN ({placeholders})
                    ORDER BY Date ASC
                """
                
                cursor.execute(query, tuple(t.upper() for t in tickers))
                rows = cursor.fetchall()
                
                if not rows:
                    raise HTTPException(status_code=404, detail="No proxy chart data found")
                
                # Parse results
                if is_postgres:
                    cols = [desc[0] for desc in cursor.description]
                    parsed_rows = [dict(zip(cols, row)) for row in rows]
                else:
                    parsed_rows = [dict(row) for row in rows]
                
                # Aggregate by date
                date_map = defaultdict(lambda: {'open': 0, 'high': 0, 'low': 0, 'close': 0, 'volume': 0, 'count': 0})
                for r in parsed_rows:
                    d = r['time']
                    date_map[d]['open'] += float(r['open'])
                    date_map[d]['high'] += float(r['high'])
                    date_map[d]['low'] += float(r['low'])
                    date_map[d]['close'] += float(r['close'])
                    date_map[d]['volume'] += float(r['volume'])
                    date_map[d]['count'] += 1
                
                # Compute averages, only keep dates where most proxy tickers have data
                min_required = max(1, divisor // 2)
                result = []
                for date in sorted(date_map.keys()):
                    agg = date_map[date]
                    if agg['count'] >= min_required:
                        result.append({
                            'time': date,
                            'open': agg['open'] / divisor,
                            'high': agg['high'] / divisor,
                            'low': agg['low'] / divisor,
                            'close': agg['close'] / divisor,
                            'volume': agg['volume'] / divisor
                        })
                
                return result
            
            # Standard Single Ticker Query
            query = """
                SELECT Date as time, Open as open, High as high, Low as low, Close as close, Volume as volume
                FROM daily_ohlcv
                WHERE Ticker = ?
                ORDER BY Date ASC
            """
            if is_postgres:
                query = query.replace('?', '%s')
                cursor.execute(query, (ticker.upper(),))
                rows = cursor.fetchall()
                cols = [desc[0] for desc in cursor.description]
                result = [dict(zip(cols, row)) for row in rows]
            else:
                cursor.execute(query, (ticker.upper(),))
                result = [dict(row) for row in cursor.fetchall()]

            if not result:
                 raise HTTPException(status_code=404, detail="No chart data found for ticker")
                 
            return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
