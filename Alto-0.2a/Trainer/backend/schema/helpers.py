import sqlite3
from typing import Optional

def _get_or_create_question_id(conn: sqlite3.Connection, question_text: str) -> int:
    cur = conn.execute("SELECT id FROM questions WHERE text = ?", (question_text,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO questions (text) VALUES (?) RETURNING id", (question_text,))
    return cur.fetchone()[0]

def _get_topic_id(conn: sqlite3.Connection, topic_name: str) -> Optional[int]:
    if not topic_name:
        return None
    cur = conn.execute("SELECT id FROM topics WHERE name = ?", (topic_name,))
    row = cur.fetchone()
    return row[0] if row else None

def _get_section_id(conn: sqlite3.Connection, section_name: str) -> Optional[int]:
    if not section_name:
        return None
    cur = conn.execute("SELECT id FROM sections WHERE name = ?", (section_name,))
    row = cur.fetchone()
    return row[0] if row else None

def _get_fallback_id(conn: sqlite3.Connection, fallback_name: str) -> Optional[int]:
    if not fallback_name:
        return None
    cur = conn.execute("SELECT id FROM fallbacks WHERE name = ?", (fallback_name,))
    row = cur.fetchone()
    return row[0] if row else None

def _get_topic_name(conn: sqlite3.Connection, topic_id: Optional[int]) -> str:
    if topic_id is None:
        return ""
    cur = conn.execute("SELECT name FROM topics WHERE id = ?", (topic_id,))
    row = cur.fetchone()
    return row[0] if row else ""

def _get_section_name(conn: sqlite3.Connection, section_id: Optional[int]) -> str:
    if section_id is None:
        return ""
    cur = conn.execute("SELECT name FROM sections WHERE id = ?", (section_id,))
    row = cur.fetchone()
    return row[0] if row else ""

def _get_fallback_name(conn: sqlite3.Connection, fallback_id: Optional[int]) -> str:
    if fallback_id is None:
        return ""
    cur = conn.execute("SELECT name FROM fallbacks WHERE id = ?", (fallback_id,))
    row = cur.fetchone()
    return row[0] if row else ""