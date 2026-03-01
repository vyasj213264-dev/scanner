import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from api.models.user import User, UserEvent
from api.routers.auth import require_user
from api.database import get_db, fetch_all, fetch_one
from api.config import DATABASE_URL

router = APIRouter(prefix="/api/v1", tags=["Analytics"])

@router.post("/events", summary="Log a user event")
def log_user_event(event: UserEvent, user: User = Depends(require_user)):
    """Logs an action performed by the user (e.g., viewed chart, ran scanner)."""
    if not user.session_id:
        return {"status": "ignored", "reason": "No active session"}

    with get_db() as conn:
        cursor = conn.cursor()
        sql = "INSERT INTO user_events (session_id, user_id, event_type, event_data) VALUES (?, ?, ?, ?)"
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            sql = sql.replace('?', '%s')
            
        cursor.execute(sql, (user.session_id, user.id, event.event_type, event.event_data))
        
        # Also update the last_active_time on the session
        update_session = "UPDATE user_sessions SET last_active_time = CURRENT_TIMESTAMP WHERE id = ?"
        if DATABASE_URL and DATABASE_URL.startswith("postgres"):
            update_session = update_session.replace('?', '%s')
        elif not DATABASE_URL or DATABASE_URL.startswith("sqlite"):
            update_session = "UPDATE user_sessions SET last_active_time = datetime('now') WHERE id = ?"
            
        cursor.execute(update_session, (user.session_id,))
        conn.commit()
        
    return {"status": "logged"}


@router.get("/admin/stats", summary="Get aggregated user stats (Magic URL)")
def get_admin_stats():
    """Returns aggregated statistics about user activity for the magic URL dashboard."""
    # 1. Total users
    total_users_row = fetch_one("SELECT COUNT(*) as count FROM users")
    total_users = total_users_row["count"] if total_users_row else 0
    
    # 2. Recent logins (last 50 sessions)
    recent_sessions_raw = fetch_all("""
        SELECT s.id, u.email, u.name, s.login_time, s.last_active_time
        FROM user_sessions s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.login_time DESC
        LIMIT 50
    """)
    
    # Calculate duration in seconds for each session
    from datetime import datetime
    recent_sessions = []
    for s in recent_sessions_raw:
        # fetch_all returns dictionaries
        login = s['login_time']
        active = s['last_active_time']
        
        duration = 0
        try:
            # Handle both string timestamps (SQLite) and datetime objects (Postgres)
            if isinstance(login, str):
                login_dt = datetime.fromisoformat(login.replace('Z', '+00:00'))
            else:
                login_dt = login
                
            if isinstance(active, str):
                active_dt = datetime.fromisoformat(active.replace('Z', '+00:00'))
            else:
                active_dt = active
                
            duration = int((active_dt - login_dt).total_seconds())
        except:
            pass
            
        s_plus = dict(s)
        s_plus['duration_seconds'] = max(0, duration)
        recent_sessions.append(s_plus)
    
    # 3. Most popular charts/actions today
    # (SQLite and Postgres timestamps differ, we'll just do global top for simplicity right now)
    top_events = fetch_all("""
        SELECT event_type, event_data, COUNT(*) as count 
        FROM user_events 
        GROUP BY event_type, event_data 
        ORDER BY count DESC 
        LIMIT 20
    """)

    # 4. All registered users
    all_users = fetch_all("SELECT id, email, name, created_at FROM users ORDER BY created_at DESC")

    # 5. Ticker engagement analysis (time spent per ticker per day)
    all_events = fetch_all("""
        SELECT e.user_id, u.email, e.session_id, e.event_type, e.event_data, e.created_at, s.last_active_time
        FROM user_events e
        JOIN user_sessions s ON e.session_id = s.id
        JOIN users u ON e.user_id = u.id
        ORDER BY e.user_id, e.session_id, e.created_at ASC
    """)
    
    ticker_time = {} # (date, user_email, ticker) -> total_seconds
    for i in range(len(all_events)):
        ev = all_events[i]
        if ev['event_type'] not in ('view_stock_detail', 'view_chart'):
            continue
            
        try:
            # event_data can be double-stringified depending on some client libs
            data = ev['event_data']
            if data and data.startswith('{'):
                data = json.loads(data)
                ticker = data.get('ticker')
            else:
                ticker = data
        except:
            ticker = ev['event_data']
            
        if not ticker: continue
        
        start_time = ev['created_at']
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00')) if isinstance(start_time, str) else start_time
        
        end_dt = None
        if i + 1 < len(all_events) and all_events[i+1]['session_id'] == ev['session_id']:
            next_time = all_events[i+1]['created_at']
            end_dt = datetime.fromisoformat(next_time.replace('Z', '+00:00')) if isinstance(next_time, str) else next_time
        else:
            last_active = ev['last_active_time']
            end_dt = datetime.fromisoformat(last_active.replace('Z', '+00:00')) if isinstance(last_active, str) else last_active
            
        if start_dt and end_dt:
            duration = int((end_dt - start_dt).total_seconds())
            duration = max(5, min(duration, 1800)) # Cap at 30 mins
            
            day = start_dt.strftime('%Y-%m-%d')
            key = (day, ev['email'], ticker)
            ticker_time[key] = ticker_time.get(key, 0) + duration
            
    top_ticker_time = sorted([
        {"day": k[0], "user": k[1], "ticker": k[2], "seconds": v}
        for k, v in ticker_time.items()
    ], key=lambda x: x['seconds'], reverse=True)[:50]

    return {
        "total_users": total_users,
        "recent_sessions": recent_sessions,
        "top_events": top_events,
        "all_users": all_users,
        "top_ticker_time": top_ticker_time
    }
