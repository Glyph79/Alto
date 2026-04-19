import sqlite3
import datetime
from typing import List, Dict, Optional, Tuple

def get_variants(conn: sqlite3.Connection, limit: int, offset: int) -> Tuple[List[Dict], int]:
    cur = conn.execute("SELECT COUNT(*) FROM variant_groups")
    total = cur.fetchone()[0]
    cur = conn.execute("""
        SELECT vg.id, vg.name,
               GROUP_CONCAT(vw.word, ',') as words
        FROM variant_groups vg
        LEFT JOIN variant_words vw ON vw.group_id = vg.id
        GROUP BY vg.id
        ORDER BY vg.id
        LIMIT ? OFFSET ?
    """, (limit, offset))
    variants = []
    for row in cur:
        words = row[2].split(',') if row[2] else []
        variants.append({
            "id": row[0],
            "name": row[1],
            "words": words
        })
    return variants, total

def add_variant(conn: sqlite3.Connection, name: str, words: List[str]) -> int:
    try:
        cur = conn.execute(
            "INSERT INTO variant_groups (name) VALUES (?) RETURNING id",
            (name,)
        )
        group_id = cur.fetchone()[0]
        for word in words:
            conn.execute("INSERT INTO variant_words (word, group_id) VALUES (?, ?)", (word, group_id))
        conn.commit()
        return group_id
    except Exception:
        conn.rollback()
        raise

def update_variant(conn: sqlite3.Connection, variant_id: int, name: str, words: List[str]):
    try:
        conn.execute("UPDATE variant_groups SET name = ? WHERE id = ?", (name, variant_id))
        conn.execute("DELETE FROM variant_words WHERE group_id = ?", (variant_id,))
        for word in words:
            conn.execute("INSERT INTO variant_words (word, group_id) VALUES (?, ?)", (word, variant_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def delete_variant(conn: sqlite3.Connection, variant_id: int):
    conn.execute("DELETE FROM variant_groups WHERE id = ?", (variant_id,))
    conn.commit()