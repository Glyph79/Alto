import sqlite3
import datetime
from typing import List, Dict, Optional
from .blob_utils import store_blob, release_blob, get_blob_data
from ..utils.msgpack_helpers import pack_array, unpack_array

def get_fallbacks(conn: sqlite3.Connection) -> List[Dict]:
    cur = conn.execute("""
        SELECT f.id, f.name, f.description, f.answer_count,
               (SELECT COUNT(*) FROM (
                   SELECT id FROM groups WHERE fallback_id = f.id
                   UNION ALL
                   SELECT id FROM followup_nodes WHERE fallback_id = f.id
               )) as usage_count
        FROM fallbacks f
        ORDER BY f.id
    """)
    fallbacks = []
    for row in cur:
        fallbacks.append({
            "id": row[0],
            "name": row[1] if row[1] is not None else "",
            "description": row[2],
            "answer_count": row[3],
            "usage_count": row[4]
        })
    return fallbacks

def get_fallback_by_id(conn: sqlite3.Connection, fallback_id: int) -> Dict:
    cur = conn.execute(
        "SELECT id, name, description, answers_blob_id, answer_count FROM fallbacks WHERE id = ?",
        (fallback_id,)
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Fallback {fallback_id} not found")
    answers_raw = get_blob_data(conn, row[3])
    answers = unpack_array(answers_raw) if answers_raw else []
    return {
        "id": row[0],
        "name": row[1] if row[1] is not None else "",
        "description": row[2],
        "answers": answers,
        "answer_count": row[4]
    }

def create_fallback(conn: sqlite3.Connection, name: str, description: str, answers: List[str]) -> int:
    if name is None or name.strip() == "":
        db_name = None
    else:
        db_name = name.strip()
    answers_raw = pack_array(answers)
    a_id = store_blob(conn, answers_raw, normalise=False)
    try:
        cur = conn.execute(
            "INSERT INTO fallbacks (name, description, answers_blob_id, answer_count) VALUES (?, ?, ?, ?) RETURNING id",
            (db_name, description, a_id, len(answers))
        )
        fallback_id = cur.fetchone()[0]
        conn.commit()
        return fallback_id
    except Exception:
        conn.rollback()
        raise

def update_fallback(conn: sqlite3.Connection, fallback_id: int, name: str, description: str, answers: List[str]):
    if name is None or name.strip() == "":
        db_name = None
    else:
        db_name = name.strip()
    answers_raw = pack_array(answers)
    new_a_id = store_blob(conn, answers_raw, normalise=False)
    cur = conn.execute("SELECT answers_blob_id FROM fallbacks WHERE id = ?", (fallback_id,))
    old_a_id = cur.fetchone()[0]
    try:
        conn.execute(
            "UPDATE fallbacks SET name = ?, description = ?, answers_blob_id = ?, answer_count = ? WHERE id = ?",
            (db_name, description, new_a_id, len(answers), fallback_id)
        )
        release_blob(conn, old_a_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def delete_fallback(conn: sqlite3.Connection, fallback_id: int):
    cur = conn.execute("SELECT answers_blob_id FROM fallbacks WHERE id = ?", (fallback_id,))
    row = cur.fetchone()
    if row:
        release_blob(conn, row[0])
    conn.execute("DELETE FROM fallbacks WHERE id = ?", (fallback_id,))
    conn.commit()

def get_groups_by_fallback(conn: sqlite3.Connection, fallback_id: int) -> List[Dict]:
    cur = conn.execute("""
        SELECT g.id, g.group_name
        FROM groups g
        WHERE g.fallback_id = ?
        ORDER BY g.group_name
    """, (fallback_id,))
    groups = []
    for row in cur:
        groups.append({
            "id": row[0],
            "group_name": row[1]
        })
    return groups

def get_nodes_by_fallback(conn: sqlite3.Connection, fallback_id: int) -> List[Dict]:
    cur = conn.execute("""
        SELECT fn.id, fn.branch_name, g.group_name
        FROM followup_nodes fn
        JOIN groups g ON fn.group_id = g.id
        WHERE fn.fallback_id = ?
        ORDER BY fn.branch_name
    """, (fallback_id,))
    nodes = []
    for row in cur:
        nodes.append({
            "id": row[0],
            "branch_name": row[1],
            "group_name": row[2]
        })
    return nodes