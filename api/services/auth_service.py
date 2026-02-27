"""
Auth service — user management + JWT creation/verification.
DB tables: users, watchlists, watchlist_stocks
"""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from api.models.user import User

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

DB_PATH = os.environ.get("DB_PATH", "scanner.db")


# ---------------------------------------------------------------------------
# DB Initialisation
# ---------------------------------------------------------------------------

def init_user_tables() -> None:
    """Create auth/watchlist tables if they don't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT UNIQUE NOT NULL,
                name       TEXT,
                picture    TEXT,
                google_id  TEXT UNIQUE,
                plan       TEXT DEFAULT 'free',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS watchlists (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                name       TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS watchlist_stocks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                watchlist_id  INTEGER NOT NULL,
                ticker        TEXT NOT NULL,
                added_at      TEXT DEFAULT (datetime('now')),
                UNIQUE (watchlist_id, ticker),
                FOREIGN KEY (watchlist_id) REFERENCES watchlists(id)
            );
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def get_or_create_user(google_id: str, email: str, name: str, picture: str) -> User:
    """Upsert a user from Google profile data. Returns the user dict."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        # Try to find by google_id
        row = conn.execute(
            "SELECT * FROM users WHERE google_id = ?", (google_id,)
        ).fetchone()
        if row is None:
            # Try by email (account existed before OAuth)
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
        if row is None:
            # Create new user
            conn.execute(
                "INSERT INTO users (email, name, picture, google_id) VALUES (?,?,?,?)",
                (email, name, picture, google_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
        else:
            # Update name/picture/google_id in case they changed
            conn.execute(
                "UPDATE users SET name=?, picture=?, google_id=? WHERE id=?",
                (name, picture, google_id, row["id"]),
            )
            conn.commit()
        return User(**dict(row))


def get_user_by_id(user_id: int) -> Optional[User]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return User(**dict(row)) if row else None


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    """Returns user_id or None if invalid/expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None
