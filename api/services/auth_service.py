"""
Auth service — user management + JWT creation/verification.
DB tables: users, watchlists, watchlist_stocks
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from api.models.user import User
from api.database import get_db, get_user_db, fetch_one, fetch_all
from api.config import DATABASE_URL

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30


# ---------------------------------------------------------------------------
# DB Initialisation
# ---------------------------------------------------------------------------

def init_user_tables() -> None:
    """Create auth/watchlist tables if they don't exist."""
    is_postgres = DATABASE_URL and DATABASE_URL.startswith("postgres")
    
    # Postgres syntax vs SQLite syntax
    user_id_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    wl_id_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    wls_id_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    
    now_func = "DEFAULT CURRENT_TIMESTAMP" if is_postgres else "DEFAULT (datetime('now'))"
    
    with get_user_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                id         {user_id_type},
                email      TEXT UNIQUE NOT NULL,
                name       TEXT,
                picture    TEXT,
                google_id  TEXT UNIQUE,
                plan       TEXT DEFAULT 'free',
                created_at TIMESTAMP {now_func}
            );
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS watchlists (
                id         {wl_id_type},
                user_id    INTEGER NOT NULL,
                name       TEXT NOT NULL,
                created_at TIMESTAMP {now_func},
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS watchlist_stocks (
                id            {wls_id_type},
                watchlist_id  INTEGER NOT NULL,
                ticker        TEXT NOT NULL,
                added_at      TIMESTAMP {now_func},
                UNIQUE (watchlist_id, ticker),
                FOREIGN KEY (watchlist_id) REFERENCES watchlists(id)
            );
        """)
        
        # Admin Analytics Tables
        session_id_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        event_id_type = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id               {session_id_type},
                user_id          INTEGER NOT NULL,
                login_time       TIMESTAMP {now_func},
                last_active_time TIMESTAMP {now_func},
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS user_events (
                id          {event_id_type},
                session_id  INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                event_type  TEXT NOT NULL,
                event_data  TEXT,
                created_at  TIMESTAMP {now_func},
                FOREIGN KEY (session_id) REFERENCES user_sessions(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)

        # 5. Magic Watchlist Items (for /test page)
        try:
            print("📦 Ensuring magic_watchlist_items table exists...")
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS magic_watchlist_items (
                    id          {event_id_type},
                    section     TEXT NOT NULL,
                    ticker      TEXT NOT NULL,
                    sort_order  INTEGER DEFAULT 0,
                    updated_at  TIMESTAMP {now_func}
                );
            """)
            print("✅ magic_watchlist_items table verified.")
        except Exception as e:
            print(f"❌ Error creating magic_watchlist_items: {e}")
        
        # Add is_admin column to users if it doesn't exist
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
            print("✅ users.is_admin column verified.")
        except Exception:
            pass # Column likely exists
            
        conn.commit()
        print("💾 Database initialization complete.")


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def get_or_create_user(google_id: str, email: str, name: str, picture: str) -> User:
    """Upsert a user from Google profile data. Returns the user dict."""
    is_postgres = DATABASE_URL and DATABASE_URL.startswith("postgres")
    
    # Try to find by google_id
    row = fetch_one("SELECT * FROM users WHERE google_id = ?", (google_id,))
    
    if row is None:
        # Try by email (account existed before OAuth)
        row = fetch_one("SELECT * FROM users WHERE email = ?", (email,))
        
    with get_user_db() as conn:
        cursor = conn.cursor()
        if row is None:
            # Create new user
            sql = "INSERT INTO users (email, name, picture, google_id) VALUES (?,?,?,?) RETURNING id, email, name, picture, google_id, plan, is_admin, created_at"
            if is_postgres:
                sql = sql.replace('?', '%s')
            cursor.execute(sql, (email, name, picture, google_id))
            inserted_row = cursor.fetchone()
            conn.commit()
            
            if inserted_row is None:
                # Fallback for old SQLite
                last_id = cursor.lastrowid
                sql_fetch = "SELECT * FROM users WHERE id = ?"
                if is_postgres: sql_fetch = sql_fetch.replace('?', '%s')
                cursor.execute(sql_fetch, (last_id,))
                inserted_row = cursor.fetchone()
                
            return User(**dict(inserted_row))
        else:
            # Update name/picture/google_id in case they changed
            sql = "UPDATE users SET name=?, picture=?, google_id=? WHERE id=?"
            if is_postgres: sql = sql.replace('?', '%s')
            cursor.execute(sql, (name, picture, google_id, row["id"]))
            conn.commit()
            
            # Re-fetch mutated row
            updated_row = fetch_one("SELECT * FROM users WHERE id = ?", (row["id"],))
            user = User(**dict(updated_row))
            
        # Create a new session record on login
        session_sql = "INSERT INTO user_sessions (user_id) VALUES (?) RETURNING id"
        if is_postgres: session_sql = session_sql.replace('?', '%s')
        
        cursor.execute(session_sql, (user.id,))
        session_row = cursor.fetchone()
        conn.commit()
        
        if session_row is None:
            # Fallback for old SQLite
            last_id = cursor.lastrowid
            user.session_id = last_id
        else:
            user.session_id = dict(session_row)["id"]
            
        return user


def get_user_by_id(user_id: int) -> Optional[User]:
    row = fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
    return User(**dict(row)) if row else None


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, session_id: Optional[int] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire}
    if session_id:
        payload["session_id"] = session_id
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Returns dict with user_id and session_id, or empty dict if invalid/expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"user_id": int(payload["sub"]), "session_id": payload.get("session_id")}
    except (JWTError, KeyError, ValueError):
        return {}
