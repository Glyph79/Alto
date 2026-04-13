# web/auth/auth.py
import sqlite3
import os
import hashlib
import secrets
from typing import Optional

from alto.config import USERS_DIR   # import hardcoded path

DB_PATH = os.path.join(USERS_DIR, 'users.db')

def ensure_users_dir():
    os.makedirs(USERS_DIR, exist_ok=True)

def _get_connection():
    ensure_users_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256((salt + password).encode())
    return f"{salt}${hash_obj.hexdigest()}"

def _verify_password(password: str, password_hash: str) -> bool:
    salt, hash_val = password_hash.split('$')
    return hashlib.sha256((salt + password).encode()).hexdigest() == hash_val

def register_user(username: str, password: str) -> tuple[bool, str]:
    if not username or not password:
        return False, "Username and password required"
    if len(password) < 6:
        return False, "Password must be at least 6 characters"
    try:
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, _hash_password(password))
            )
            conn.commit()
        return True, "User registered successfully"
    except sqlite3.IntegrityError:
        return False, "Username already exists"

def authenticate_user(username: str, password: str) -> Optional[int]:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if row and _verify_password(password, row['password_hash']):
            return row['id']
    return None

def user_exists(user_id: int) -> bool:
    with _get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        return row is not None

init_db()