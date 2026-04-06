import sqlite3
from typing import List, Dict, Optional
from .helpers import _get_topic_id, _get_section_id

def get_topics_list(conn: sqlite3.Connection) -> List[str]:
    cur = conn.execute("SELECT name FROM topics ORDER BY name")
    return [row[0] for row in cur]

def add_topic(conn: sqlite3.Connection, name: str, section_name: Optional[str] = None) -> int:
    section_id = _get_section_id(conn, section_name) if section_name else None
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute("SELECT id FROM topics WHERE name = ?", (name,))
        if cur.fetchone() is not None:
            raise ValueError(f"Topic '{name}' already exists")
        cur = conn.execute(
            "INSERT INTO topics (name, section_id) VALUES (?, ?) RETURNING id",
            (name, section_id)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    except Exception:
        conn.rollback()
        raise

def rename_topic(conn: sqlite3.Connection, old_name: str, new_name: str):
    conn.execute("UPDATE topics SET name = ? WHERE name = ?", (new_name, old_name))
    conn.commit()

def delete_topic(conn: sqlite3.Connection, name: str, action: str = "reassign", target: Optional[str] = None):
    topic_id = _get_topic_id(conn, name)
    if not topic_id:
        raise ValueError(f"Topic '{name}' not found")
    target_id = None
    if target:
        target_id = _get_topic_id(conn, target)
        if not target_id:
            raise ValueError(f"Target topic '{target}' not found")
    if action == "delete_groups":
        cur = conn.execute("SELECT id FROM groups WHERE topic_id = ?", (topic_id,))
        group_ids = [row[0] for row in cur.fetchall()]
        # Delete groups will cascade to followups etc.
        for gid in group_ids:
            conn.execute("DELETE FROM groups WHERE id = ?", (gid,))
        conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        conn.commit()
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("UPDATE groups SET topic_id = ? WHERE topic_id = ?", (target_id, topic_id))
        conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def get_topic_groups(conn: sqlite3.Connection, topic_name: str) -> List[Dict]:
    topic_id = _get_topic_id(conn, topic_name)
    if not topic_id:
        return []
    cur = conn.execute("""
        SELECT g.id, g.group_name,
               (SELECT COUNT(*) FROM group_questions WHERE group_id = g.id) as question_count,
               g.answer_count,
               COALESCE(s.name, '') as section
        FROM groups g
        LEFT JOIN sections s ON g.section_id = s.id
        WHERE g.topic_id = ?
        ORDER BY g.id
    """, (topic_id,))
    groups = []
    for row in cur:
        groups.append({
            "id": row[0],
            "group_name": row[1],
            "question_count": row[2],
            "answer_count": row[3],
            "section": row[4]
        })
    return groups