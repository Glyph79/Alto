import sqlite3
import datetime
from typing import List, Dict, Optional
from .helpers import _get_section_id
from .compression import compress_blob, decompress_blob

def get_variants(conn: sqlite3.Connection) -> List[Dict]:
    cur = conn.execute("""
        SELECT vg.id, vg.name,
               COALESCE(s.name, '') as section,
               GROUP_CONCAT(vw.word, ',') as words
        FROM variant_groups vg
        LEFT JOIN sections s ON vg.section_id = s.id
        LEFT JOIN variant_words vw ON vw.group_id = vg.id
        GROUP BY vg.id
        ORDER BY vg.id
    """)
    variants = []
    for row in cur:
        words = row[3].split(',') if row[3] else []
        variants.append({
            "id": row[0],
            "name": row[1],
            "section": row[2],
            "words": words
        })
    return variants

def add_variant(conn: sqlite3.Connection, name: str, section_name: Optional[str], words: List[str]) -> int:
    section_id = _get_section_id(conn, section_name) if section_name else None
    now = datetime.datetime.now().isoformat()
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "INSERT INTO variant_groups (name, section_id, created_at) VALUES (?, ?, ?) RETURNING id",
            (name, section_id, now)
        )
        group_id = cur.fetchone()[0]
        for word in words:
            conn.execute("INSERT INTO variant_words (word, group_id) VALUES (?, ?)", (word, group_id))
        conn.commit()
        return group_id
    except Exception:
        conn.rollback()
        raise

def update_variant(conn: sqlite3.Connection, variant_id: int, name: str, section_name: Optional[str], words: List[str]):
    section_id = _get_section_id(conn, section_name) if section_name else None
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE variant_groups SET name = ?, section_id = ? WHERE id = ?",
            (name, section_id, variant_id)
        )
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