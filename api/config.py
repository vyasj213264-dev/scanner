"""
Central configuration for StockScans API.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file (if present)
load_dotenv()

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scanner.db")

# --- Universe ---
UNIVERSE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "master_universe.txt")

# --- CORS ---
CORS_ORIGINS = ["*"]

# --- Pagination ---
DEFAULT_SCAN_LIMIT = 5000
MAX_SCAN_LIMIT = 5000

# --- App metadata ---
APP_TITLE = "StockScans API"
APP_DESCRIPTION = "Production-grade stock scanner API for 3,100+ US equities."
APP_VERSION = "1.0.0"
