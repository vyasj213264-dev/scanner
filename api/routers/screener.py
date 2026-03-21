"""
Custom Screener router — dynamic SQL generation from JSON filter tree.
"""
from datetime import datetime
from typing import List, Optional, Any, Union
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
import json
import os

from api.models.user import User
from api.routers.auth import require_user
from api.database import fetch_all, fetch_one, get_db
from api.models.scanner import StockResult
from api.services.scanner_service import BASELINE_FILTER, get_baseline_filter
from api.config import DATABASE_URL

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
    created_at: Union[str, datetime]

# ── Services ──────────────────────────────────────────────────────────────────

def init_screener_tables():
    is_postgres = DATABASE_URL and DATABASE_URL.startswith("postgres")
    id_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    now_func = "DEFAULT CURRENT_TIMESTAMP" if is_postgres else "DEFAULT (datetime('now'))"
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS saved_screens (
                id         {id_type},
                user_id    INTEGER NOT NULL,
                name       TEXT NOT NULL,
                payload    TEXT NOT NULL,
                created_at TIMESTAMP {now_func},
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        conn.commit()

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

def build_sql(payload: ScreenPayload, market: str = "US") -> tuple[str, list]:
    baseline = get_baseline_filter(market)
    where_clauses = [baseline, f"Market = ?"]
    params = [market]
    
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
def run_custom_screen(payload: ScreenPayload, market: str = "US"): # Open endpoint, free to run unless we paywall
    sql, params = build_sql(payload, market=market.upper())
    rows = fetch_all(sql, params)
    results = [StockResult.model_validate(r) for r in rows if r.get("Ticker")]
    return {
        "count": len(results),
        "data": results
    }

@router.get("/saved", response_model=List[SavedScreenOut], summary="List saved screens")
def list_saved_screens(user: User = Depends(require_user)):
    sql = "SELECT id, name, payload, created_at FROM saved_screens WHERE user_id = ? ORDER BY created_at DESC"
    if DATABASE_URL and DATABASE_URL.startswith("postgres"):
        sql = sql.replace('?', '%s')
        
    rows = fetch_all(sql, (user.id,))
    
    screens = []
    for r in rows:
        screens.append({
            "id": r["id"],
            "name": r["name"],
            "payload": json.loads(r["payload"]),
            "created_at": str(r["created_at"])
        })
    return screens

@router.post("/saved", response_model=SavedScreenOut, summary="Save a custom screen")
def save_screen(body: SavedScreenCreate, user: User = Depends(require_user)):
    payload_str = body.payload.model_dump_json()
    is_postgres = DATABASE_URL and DATABASE_URL.startswith("postgres")
    
    with get_db() as conn:
        cursor = conn.cursor()
        sql = "INSERT INTO saved_screens (user_id, name, payload) VALUES (?, ?, ?) RETURNING id, name, payload, created_at"
        if is_postgres:
            sql = sql.replace('?', '%s')
            
        cursor.execute(sql, (user.id, body.name.strip(), payload_str))
        inserted_row = cursor.fetchone()
        conn.commit()
        
        if inserted_row is None:
            # Fallback for old SQLite
            last_id = cursor.lastrowid
            sql_fetch = "SELECT id, name, payload, created_at FROM saved_screens WHERE id = ?"
            if is_postgres: sql_fetch = sql_fetch.replace('?', '%s')
            cursor.execute(sql_fetch, (last_id,))
            inserted_row = cursor.fetchone()
            
    return {
        "id": inserted_row[0] if isinstance(inserted_row, tuple) else inserted_row["id"],
        "name": inserted_row[1] if isinstance(inserted_row, tuple) else inserted_row["name"],
        "payload": json.loads(inserted_row[2] if isinstance(inserted_row, tuple) else inserted_row["payload"]),
        "created_at": str(inserted_row[3] if isinstance(inserted_row, tuple) else inserted_row["created_at"])
    }

@router.delete("/saved/{screen_id}", summary="Delete saved screen")
def delete_saved_screen(screen_id: int, user: User = Depends(require_user)):
    with get_db() as conn:
        cursor = conn.cursor()
        sql = "DELETE FROM saved_screens WHERE id = ? AND user_id = ?"
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            sql = sql.replace('?', '%s')
        
        cursor.execute(sql, (screen_id, user.id))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Screen not found")
        return {"deleted": screen_id}
