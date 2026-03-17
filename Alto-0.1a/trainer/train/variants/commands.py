"""Commands for managing word variants."""
import json
import datetime
from typing import Dict, List
from train.model import get_model

def cmd_get_variants(name: str, **kwargs) -> List[Dict]:
    """Return all variant groups (id, topic, words)."""
    try:
        model = get_model(name)
        cur = model.conn.execute("""
            SELECT g.id, g.topic, GROUP_CONCAT(w.word, ',') as words
            FROM variant_groups g
            LEFT JOIN variant_words w ON w.group_id = g.id
            GROUP BY g.id
            ORDER BY g.id
        """)
        variants = []
        for row in cur:
            words = row[2].split(',') if row[2] else []
            variants.append({"id": row[0], "topic": row[1], "words": words})
        return variants
    except Exception as e:
        return {"error": str(e)}

def cmd_add_variant(name: str, data: str, **kwargs) -> Dict:
    """Add a new variant group. Data must contain 'topic' (or null) and 'words' (list)."""
    try:
        data_dict = json.loads(data)
        topic = data_dict.get("topic")  # None allowed
        words = data_dict.get("words", [])
        if not isinstance(words, list) or not words:
            return {"error": "Words must be a non‑empty list"}

        model = get_model(name)
        conn = model.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Insert group
            now = datetime.datetime.now().isoformat()
            cur = conn.execute(
                "INSERT INTO variant_groups (topic, created_at) VALUES (?, ?) RETURNING id",
                (topic, now)
            )
            group_id = cur.fetchone()[0]
            # Insert words
            for word in words:
                conn.execute(
                    "INSERT INTO variant_words (word, group_id) VALUES (?, ?)",
                    (word, group_id)
                )
            conn.commit()
            return {"status": "ok", "id": group_id}
        except Exception:
            conn.rollback()
            raise
    except Exception as e:
        return {"error": str(e)}

def cmd_update_variant(name: str, variant_id: int, data: str, **kwargs) -> Dict:
    """Update an existing variant group."""
    try:
        data_dict = json.loads(data)
        topic = data_dict.get("topic")
        words = data_dict.get("words", [])
        if not isinstance(words, list) or not words:
            return {"error": "Words must be a non‑empty list"}

        model = get_model(name)
        conn = model.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Update topic
            conn.execute(
                "UPDATE variant_groups SET topic = ? WHERE id = ?",
                (topic, variant_id)
            )
            # Delete old words
            conn.execute("DELETE FROM variant_words WHERE group_id = ?", (variant_id,))
            # Insert new words
            for word in words:
                conn.execute(
                    "INSERT INTO variant_words (word, group_id) VALUES (?, ?)",
                    (word, variant_id)
                )
            conn.commit()
            return {"status": "ok"}
        except Exception:
            conn.rollback()
            raise
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_variant(name: str, variant_id: int, **kwargs) -> Dict:
    """Delete a variant group (cascades to words)."""
    try:
        model = get_model(name)
        model.conn.execute("DELETE FROM variant_groups WHERE id = ?", (variant_id,))
        model.conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}