"""
Portfolio Simulator API Router
===============================
Endpoints for the US Portfolio Simulator:
- GET  /variants       — List all 16 variants with summary metrics
- GET  /{variant_id}   — Full result for one variant
- POST /simulate       — Trigger re-computation of all 16 variants
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


@router.get("/variants", summary="List all 16 portfolio variants with summary metrics")
def list_variants():
    """Returns summary data for all 16 strategy variants."""
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
                "sim_period": result.get('sim_period', {}),
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


@router.post("/simulate", summary="Trigger simulation instructions")
def trigger_simulation():
    """Tells the user that simulations must now be run via GitHub Actions."""
    return {
        "status": "warning",
        "message": "Due to massive memory requirements (1.5GB+), the simulation engine has been permanently decoupled from this Web API. It now runs on your robust 7GB GitHub Runners.\\n\\nTo run the simulation manually:\\n1. Go to your GitHub Repository.\\n2. Click the 'Actions' tab.\\n3. Select 'Portfolio Simulator Engine'.\\n4. Click 'Run workflow'.\\n\\nThe results will automatically populate here once finished! (It will also automatically run every night during standard ingestion)."
    }
