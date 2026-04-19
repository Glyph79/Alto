"""Helpers for global routes database with default weather routes."""
import os
import sqlite3
import json
import time
from typing import List, Dict

ROUTES_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "routes.db")

# Default activation phrases for the weather module
DEFAULT_ROUTES = [
    {
        "module_name": "weather",
        "variants": [
            "weather",
            "temperature",
            "forecast",
            "what's the weather",
            "how's the weather",
            "weather today",
            "current weather",
            "weather report",
            "is it raining",
            "will it rain",
            "temperature outside",
            "how hot is it",
            "how cold is it",
            "weather conditions",
            "weather in my area"
        ]
    }
]

def init_routes_db():
    """Create the routes table if it doesn't exist and insert default routes if empty."""
    conn = sqlite3.connect(ROUTES_DB_PATH)
    try:
        # Create table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY,
                module_name TEXT NOT NULL,
                variants TEXT NOT NULL   -- JSON array of phrases
            )
        """)
        conn.commit()

        # Check if table is empty
        cur = conn.execute("SELECT COUNT(*) FROM routes")
        count = cur.fetchone()[0]
        if count == 0:
            # Insert default routes
            for route in DEFAULT_ROUTES:
                conn.execute(
                    "INSERT INTO routes (module_name, variants) VALUES (?, ?)",
                    (route["module_name"], json.dumps(route["variants"]))
                )
            conn.commit()
    finally:
        conn.close()

def get_routes_connection():
    """Return a new connection to the global routes DB."""
    init_routes_db()  # ensure table exists and has defaults
    return sqlite3.connect(ROUTES_DB_PATH)

def get_route_summaries() -> List[Dict]:
    conn = get_routes_connection()
    try:
        cur = conn.execute("""
            SELECT id, module_name, json_array_length(variants) as variant_count
            FROM routes
            ORDER BY id
        """)
        return [{"id": row[0], "module_name": row[1], "variant_count": row[2]} for row in cur]
    finally:
        conn.close()

def get_route_full(route_id: int) -> Dict:
    conn = get_routes_connection()
    try:
        cur = conn.execute("SELECT id, module_name, variants FROM routes WHERE id = ?", (route_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Route not found")
        return {
            "id": row[0],
            "module_name": row[1],
            "variants": json.loads(row[2])
        }
    finally:
        conn.close()

def _with_retry(func):
    """Decorator to retry on database lock errors."""
    def wrapper(*args, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))
                    continue
                raise
    return wrapper

@_with_retry
def add_route(module_name: str, variants: List[str]) -> int:
    conn = get_routes_connection()
    try:
        cur = conn.execute(
            "INSERT INTO routes (module_name, variants) VALUES (?, ?) RETURNING id",
            (module_name, json.dumps(variants))
        )
        row = cur.fetchone()
        conn.commit()
        return row[0]
    finally:
        conn.close()

@_with_retry
def update_route(route_id: int, module_name: str, variants: List[str]):
    conn = get_routes_connection()
    try:
        conn.execute(
            "UPDATE routes SET module_name = ?, variants = ? WHERE id = ?",
            (module_name, json.dumps(variants), route_id)
        )
        conn.commit()
    finally:
        conn.close()

@_with_retry
def delete_route(route_id: int):
    conn = get_routes_connection()
    try:
        conn.execute("DELETE FROM routes WHERE id = ?", (route_id,))
        conn.commit()
    finally:
        conn.close()