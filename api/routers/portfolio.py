"""
Portfolio Simulator API Router
===============================
Endpoints for the US Portfolio Simulator:
- GET  /variants       — List all 8 variants with summary metrics
- GET  /{variant_id}   — Full result for one variant
- POST /simulate       — Trigger re-computation of all 8 variants
"""

import json
import traceback
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends

from api.database import get_db
from api.routers.auth import require_user

router = APIRouter(
    prefix="/api/v1/portfolio",
    tags=["Portfolio Simulator"],
    dependencies=[Depends(require_user)]
)


def init_portfolio_tables():
    """Create the portfolio_results table if it doesn't exist."""
    with get_db() as conn:
        is_pg = hasattr(conn, 'info') or hasattr(conn, 'dsn')
        cursor = conn.cursor()

        if is_pg:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_results (
                    variant_id VARCHAR(255) PRIMARY KEY,
                    result_json TEXT,
                    computed_at VARCHAR(255),
                    data_through VARCHAR(255),
                    version VARCHAR(50) DEFAULT '1.0.0'
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_results (
                    variant_id TEXT PRIMARY KEY,
                    result_json TEXT,
                    computed_at TEXT,
                    data_through TEXT,
                    version TEXT DEFAULT '1.0.0'
                )
            """)
        conn.commit()
    print("✅ portfolio_results table initialized", flush=True)


@router.get("/variants", summary="List all 8 portfolio variants with summary metrics")
def list_variants():
    """Returns summary data for all 8 strategy variants."""
    try:
        with get_db() as conn:
            is_pg = hasattr(conn, 'info') or hasattr(conn, 'dsn')
            cursor = conn.cursor()

            query = "SELECT variant_id, result_json, computed_at, data_through FROM portfolio_results ORDER BY variant_id"
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

        if not rows:
            return {"status": "empty", "message": "No simulation results found. Run POST /simulate first.", "variants": []}

        variants = []
        for row in rows:
            result = json.loads(row['result_json'])
            metrics = result.get('metrics', {})
            variants.append({
                "variant_id": result['variant_id'],
                "variant_label": result['variant_label'],
                "config": result.get('config', {}),
                "total_return_pct": metrics.get('total_return_pct', 0),
                "cagr_pct": metrics.get('cagr_pct', 0),
                "max_drawdown_pct": metrics.get('max_drawdown_pct', 0),
                "win_rate_pct": metrics.get('win_rate_pct', 0),
                "total_trades": metrics.get('total_trades', 0),
                "profit_factor": metrics.get('profit_factor', 0),
                "expectancy_r": metrics.get('expectancy_r', 0),
                "ending_equity": metrics.get('ending_equity', 0),
                "open_positions_count": len(result.get('open_positions', [])),
                "computed_at": row.get('computed_at', ''),
                "data_through": row.get('data_through', '')
            })

        return {"status": "success", "variants": variants}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{e}\n{traceback.format_exc()}")


@router.get("/{variant_id}", summary="Get full result for a specific variant")
def get_variant(variant_id: str):
    """Returns the complete simulation result including trades, equity curve, positions, and metrics."""
    try:
        with get_db() as conn:
            is_pg = hasattr(conn, 'info') or hasattr(conn, 'dsn')
            cursor = conn.cursor()

            if is_pg:
                cursor.execute("SELECT result_json, computed_at FROM portfolio_results WHERE variant_id = %s", (variant_id,))
            else:
                import sqlite3
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT result_json, computed_at FROM portfolio_results WHERE variant_id = ?", (variant_id,))

            row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Variant '{variant_id}' not found. Run POST /simulate first.")

        row_dict = dict(row) if hasattr(row, 'keys') else {"result_json": row[0], "computed_at": row[1]}
        result = json.loads(row_dict['result_json'])
        result['computed_at'] = row_dict.get('computed_at', '')

        return {"status": "success", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{e}\n{traceback.format_exc()}")


@router.post("/simulate", summary="Trigger simulation of all 8 portfolio variants")
def trigger_simulation():
    """Runs the full portfolio simulation engine and stores results."""
    try:
        from api.services.portfolio_engine import run_all_variants, store_results

        results = run_all_variants()

        if not results:
            return {"status": "warning", "message": "No results generated. Check that QQQ and SPY data are available."}

        store_results(results)

        summary = []
        for r in results:
            m = r.get('metrics', {})
            summary.append({
                "variant_id": r['variant_id'],
                "total_return_pct": m.get('total_return_pct', 0),
                "total_trades": m.get('total_trades', 0),
                "win_rate_pct": m.get('win_rate_pct', 0),
            })

        return {
            "status": "success",
            "message": f"Simulation complete. {len(results)} variants computed.",
            "summary": summary
        }

    except Exception as e:
        print(f"Portfolio simulation error: {e}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(status_code=500, detail=f"{e}\n{traceback.format_exc()}")
