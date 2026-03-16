"""Commands for managing word variants."""
import json
from typing import Dict, List, Optional
from ..model import get_model

def cmd_get_variants(name: str, **kwargs) -> List[Dict]:
    """Return all variant groups (id, topic, words)."""
    try:
        model = get_model(name)
        cur = model.conn.execute("SELECT id, topic, words FROM word_variants ORDER BY id")
        variants = []
        for row in cur:
            variants.append({
                "id": row[0],
                "topic": row[1],
                "words": json.loads(row[2])
            })
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
        words_json = json.dumps(words, separators=(',', ':'))

        model = get_model(name)
        cur = model.conn.execute(
            "INSERT INTO word_variants (topic, words) VALUES (?, ?) RETURNING id",
            (topic, words_json)
        )
        variant_id = cur.fetchone()[0]
        model.conn.commit()
        return {"status": "ok", "id": variant_id}
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
        words_json = json.dumps(words, separators=(',', ':'))

        model = get_model(name)
        model.conn.execute(
            "UPDATE word_variants SET topic = ?, words = ? WHERE id = ?",
            (topic, words_json, variant_id)
        )
        model.conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_variant(name: str, variant_id: int, **kwargs) -> Dict:
    """Delete a variant group."""
    try:
        model = get_model(name)
        model.conn.execute("DELETE FROM word_variants WHERE id = ?", (variant_id,))
        model.conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}