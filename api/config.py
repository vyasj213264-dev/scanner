"""
Central configuration for ChartsMaze API.
"""
import os

# --- Database ---
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scanner.db")

# --- Universe ---
UNIVERSE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "master_universe.txt")

# --- CORS ---
CORS_ORIGINS = ["*"]

# --- Pagination ---
DEFAULT_SCAN_LIMIT = 20
MAX_SCAN_LIMIT = 100

# --- App metadata ---
APP_TITLE = "ChartsMaze API"
APP_DESCRIPTION = "Production-grade stock scanner API for 3,100+ US equities."
APP_VERSION = "1.0.0"
