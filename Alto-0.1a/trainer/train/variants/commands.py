"""Commands for managing word variants."""
import json
import sqlite3
from typing import Dict, List
from train.model import get_model

def cmd_get_variants(name: str, **kwargs) -> List[Dict]:
    try:
        model = get_model(name)
        return model.get_variants()
    except Exception as e:
        return {"error": str(e)}

def cmd_add_variant(name: str, data: str, **kwargs) -> Dict:
    try:
        data_dict = json.loads(data)
        variant_name = data_dict.get("name", "New Variant")
        section = data_dict.get("section")  # string or None
        words = data_dict.get("words", [])
        if not isinstance(words, list) or not words:
            return {"error": "Words must be a non‑empty list"}

        model = get_model(name)
        group_id = model.add_variant(variant_name, section, words)
        return {"status": "ok", "id": group_id}
    except sqlite3.OperationalError as e:
        return {"error": f"SQLite error (database locked or timeout): {e}"}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_variant(name: str, variant_id: int, data: str, **kwargs) -> Dict:
    try:
        data_dict = json.loads(data)
        variant_name = data_dict.get("name", "New Variant")
        section = data_dict.get("section")
        words = data_dict.get("words", [])
        if not isinstance(words, list) or not words:
            return {"error": "Words must be a non‑empty list"}

        model = get_model(name)
        model.update_variant(variant_id, variant_name, section, words)
        return {"status": "ok"}
    except sqlite3.OperationalError as e:
        return {"error": f"SQLite error (database locked or timeout): {e}"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_variant(name: str, variant_id: int, **kwargs) -> Dict:
    try:
        model = get_model(name)
        model.delete_variant(variant_id)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}