import sqlite3
from typing import List, Optional
from .helpers import _get_section_id

def get_sections_list(conn: sqlite3.Connection) -> List[str]:
    cur = conn.execute("SELECT name FROM sections ORDER BY sort_order")
    return [row[0] for row in cur]

def add_section(conn: sqlite3.Connection, name: str) -> int:
    try:
        cur = conn.execute("SELECT id FROM sections WHERE name = ?", (name,))
        if cur.fetchone() is not None:
            raise ValueError(f"Section '{name}' already exists")
        cur = conn.execute("SELECT COALESCE(MAX(sort_order), -1) FROM sections")
        max_order = cur.fetchone()[0]
        cur = conn.execute(
            "INSERT INTO sections (name, sort_order) VALUES (?, ?) RETURNING id",
            (name, max_order + 1)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    except Exception:
        conn.rollback()
        raise

def rename_section(conn: sqlite3.Connection, old_name: str, new_name: str):
    conn.execute("UPDATE sections SET name = ? WHERE name = ?", (new_name, old_name))
    conn.commit()

def delete_section(conn: sqlite3.Connection, name: str, action: str = "uncategorized", target: Optional[str] = None):
    section_id = _get_section_id(conn, name)
    if not section_id:
        raise ValueError(f"Section '{name}' not found")
    target_id = None
    if target:
        target_id = _get_section_id(conn, target)
        if not target_id:
            raise ValueError(f"Target section '{target}' not found")
    if action == "delete":
        # Delete all groups in this section (cascade deletes followups)
        conn.execute("DELETE FROM groups WHERE section_id = ?", (section_id,))
        conn.execute("UPDATE topics SET section_id = NULL WHERE section_id = ?", (section_id,))
        conn.execute("UPDATE variant_groups SET section_id = NULL WHERE section_id = ?", (section_id,))
        conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
        conn.commit()
        return
    try:
        if action == "uncategorized":
            conn.execute("UPDATE groups SET section_id = NULL WHERE section_id = ?", (section_id,))
            conn.execute("UPDATE topics SET section_id = NULL WHERE section_id = ?", (section_id,))
            conn.execute("UPDATE variant_groups SET section_id = NULL WHERE section_id = ?", (section_id,))
        elif action == "move":
            if target_id is None:
                raise ValueError("Target section required for move action")
            conn.execute("UPDATE groups SET section_id = ? WHERE section_id = ?", (target_id, section_id))
            conn.execute("UPDATE topics SET section_id = ? WHERE section_id = ?", (target_id, section_id))
            conn.execute("UPDATE variant_groups SET section_id = ? WHERE section_id = ?", (target_id, section_id))
        else:
            raise ValueError(f"Invalid action: {action}")
        conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise