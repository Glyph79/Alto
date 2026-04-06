import sqlite3
import datetime
from typing import List, Dict
from .compression import compress_blob, decompress_blob
from ..utils.msgpack_helpers import pack_array, unpack_array

def get_fallbacks(conn: sqlite3.Connection) -> List[Dict]:
    # Optimized query using UNION to count usage once
    cur = conn.execute("""
        SELECT f.id, f.name, f.description, f.answer_count,
               (SELECT COUNT(*) FROM (
                   SELECT id FROM groups WHERE fallback_id = f.id
                   UNION ALL
                   SELECT id FROM followup_nodes WHERE fallback_id = f.id
               )) as usage_count
        FROM fallbacks f
        ORDER BY f.name
    """)
    fallbacks = []
    for row in cur:
        fallbacks.append({
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "answer_count": row[3],
            "usage_count": row[4]
        })
    return fallbacks

def get_fallback_by_id(conn: sqlite3.Connection, fallback_id: int) -> Dict:
    cur = conn.execute(
        "SELECT id, name, description, answers_blob, answer_count, created_at, updated_at FROM fallbacks WHERE id = ?",
        (fallback_id,)
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Fallback {fallback_id} not found")
    answers_blob = decompress_blob(row[3])
    answers = unpack_array(answers_blob)
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "answers": answers,
        "answer_count": row[4],
        "created_at": row[5],
        "updated_at": row[6]
    }

def create_fallback(conn: sqlite3.Connection, name: str, description: str, answers: List[str]) -> int:
    answers_blob = pack_array(answers)
    compressed = compress_blob(answers_blob)
    now = datetime.datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO fallbacks (name, description, answers_blob, answer_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        (name, description, compressed, len(answers), now, now)
    )
    fallback_id = cur.fetchone()[0]
    conn.commit()
    return fallback_id

def update_fallback(conn: sqlite3.Connection, fallback_id: int, name: str, description: str, answers: List[str]):
    answers_blob = pack_array(answers)
    compressed = compress_blob(answers_blob)
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "UPDATE fallbacks SET name = ?, description = ?, answers_blob = ?, answer_count = ?, updated_at = ? WHERE id = ?",
        (name, description, compressed, len(answers), now, fallback_id)
    )
    conn.commit()

def delete_fallback(conn: sqlite3.Connection, fallback_id: int):
    conn.execute("DELETE FROM fallbacks WHERE id = ?", (fallback_id,))
    conn.commit()

def get_groups_by_fallback(conn: sqlite3.Connection, fallback_id: int) -> List[Dict]:
    cur = conn.execute("""
        SELECT g.id, g.group_name, COALESCE(s.name, '') as section
        FROM groups g
        LEFT JOIN sections s ON g.section_id = s.id
        WHERE g.fallback_id = ?
        ORDER BY g.group_name
    """, (fallback_id,))
    groups = []
    for row in cur:
        groups.append({
            "id": row[0],
            "group_name": row[1],
            "section": row[2]
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