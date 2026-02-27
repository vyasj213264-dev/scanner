"""
Custom Screener router — dynamic SQL generation from JSON filter tree.
"""
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
import json
import sqlite3
import os

from api.models.user import User
from api.routers.auth import require_user
from api.database import fetch_all
from api.models.scanner import StockResult
from api.services.scanner_service import BASELINE_FILTER

DB_PATH = os.environ.get("DB_PATH", "scanner.db")

router = APIRouter(prefix="/api/v1/screener", tags=["Custom Screener"])

# ── Models ────────────────────────────────────────────────────────────────────

class FilterCondition(BaseModel):
    field: str
    operator: str  # '=', '>', '<', '>=', '<=', 'between', 'in', 'contains'
    value: Any
    value_max: Optional[Any] = None  # For 'between'

class ScreenPayload(BaseModel):
    conditions: List[FilterCondition]
    sort_by: str = "RS_Rating"
    order: str = "desc"
    limit: int = 200

class SavedScreenCreate(BaseModel):
    name: str
    payload: ScreenPayload

class SavedScreenOut(BaseModel):
    id: int
    name: str
    payload: ScreenPayload
    created_at: str

# ── Services ──────────────────────────────────────────────────────────────────

def init_screener_tables():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS saved_screens (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                name       TEXT NOT NULL,
                payload    TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        conn.commit()

init_screener_tables()

# ── Dynamic SQL Builder ────────────────────────────────────────────────────────

ALLOWED_FIELDS = {
    "rs_rating": "RS_Rating",
    "rvol": "RVOL",
    "close": "Close",
    "market_cap": "Market_Cap",
    "adr_20": "ADR_20",
    "momentum_1m": "Momentum_1M",
    "momentum_3m": "Momentum_3M",
    "momentum_6m": "Momentum_6M",
    "momentum_1y": "Momentum_1Y",
    "pct_from_52w_high": "Pct_From_52W_High",
    "in_stage_2": "In_Stage_2",
    "gap_up": "Gap_Up",
    "gap_down": "Gap_Down",
    "sector": "Sector",
    "industry": "Industry"
}

def build_sql(payload: ScreenPayload) -> tuple[str, list]:
    where_clauses = [BASELINE_FILTER]
    params = []
    
    for cond in payload.conditions:
        if cond.field not in ALLOWED_FIELDS:
            continue
        db_col = ALLOWED_FIELDS[cond.field]
        
        # Protect against SQL Injection for operators
        op = cond.operator.lower()
        if op == '=':
            where_clauses.append(f"{db_col} = ?")
            params.append(cond.value)
        elif op == '>':
            where_clauses.append(f"{db_col} > ?")
            params.append(cond.value)
        elif op == '<':
            where_clauses.append(f"{db_col} < ?")
            params.append(cond.value)
        elif op == '>=':
            where_clauses.append(f"{db_col} >= ?")
            params.append(cond.value)
        elif op == '<=':
            where_clauses.append(f"{db_col} <= ?")
            params.append(cond.value)
        elif op == 'between':
            where_clauses.append(f"{db_col} BETWEEN ? AND ?")
            params.extend([cond.value, cond.value_max])
        elif op == 'contains':
            where_clauses.append(f"{db_col} LIKE ?")
            params.append(f"%{cond.value}%")

    # Order By
    order_col = ALLOWED_FIELDS.get(payload.sort_by, "RS_Rating")
    order_dir = "ASC" if payload.order.lower() == "asc" else "DESC"
    
    # Limit
    limit = max(1, min(payload.limit, 1000))
    
    sql = f"""
    SELECT * FROM screen_data
    WHERE {" AND ".join(where_clauses)}
    ORDER BY {order_col} {order_dir} NULLS LAST
    LIMIT {limit}
    """
    
    return sql, params

# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/run", summary="Run a custom screen dynamically")
def run_custom_screen(payload: ScreenPayload): # Open endpoint, free to run unless we paywall
    sql, params = build_sql(payload)
    rows = fetch_all(sql, params)
    results = [StockResult.model_validate(r) for r in rows if r.get("Ticker")]
    return {
        "count": len(results),
        "data": results
    }

@router.get("/saved", response_model=List[SavedScreenOut], summary="List saved screens")
def list_saved_screens(user: User = Depends(require_user)):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, payload, created_at FROM saved_screens WHERE user_id = ? ORDER BY created_at DESC",
            (user.id,)
        ).fetchall()
        
        screens = []
        for r in rows:
            screens.append({
                "id": r["id"],
                "name": r["name"],
                "payload": json.loads(r["payload"]),
                "created_at": r["created_at"]
            })
        return screens

@router.post("/saved", response_model=SavedScreenOut, summary="Save a custom screen")
def save_screen(body: SavedScreenCreate, user: User = Depends(require_user)):
    payload_str = body.payload.model_dump_json()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO saved_screens (user_id, name, payload) VALUES (?, ?, ?)",
            (user.id, body.name.strip(), payload_str)
        )
        conn.commit()
        
        row = conn.execute("SELECT * FROM saved_screens WHERE id = ?", (cur.lastrowid,)).fetchone()
        
    return {
        "id": row[0],
        "name": row[2],
        "payload": json.loads(row[3]),
        "created_at": row[4]
    }

@router.delete("/saved/{screen_id}", summary="Delete saved screen")
def delete_saved_screen(screen_id: int, user: User = Depends(require_user)):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("DELETE FROM saved_screens WHERE id = ? AND user_id = ?", (screen_id, user.id))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Screen not found")
        return {"deleted": screen_id}
