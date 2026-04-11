import json
from typing import Dict, List
from ..model import get_model

def cmd_list_fallbacks(name: str, limit: int = 20, offset: int = 0, **kwargs) -> Dict:
    try:
        model = get_model(name)
        fallbacks, total = model.get_fallbacks(limit, offset)
        return {"fallbacks": fallbacks, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        return {"error": str(e)}

def cmd_create_fallback(name: str, data: str, **kwargs) -> Dict:
    try:
        fallback_dict = json.loads(data)
        fallback_name = fallback_dict.get("name", "").strip()
        description = fallback_dict.get("description", "")
        answers = fallback_dict.get("answers", [])
        if not isinstance(answers, list) or not answers:
            return {"error": "At least one answer is required"}
        model = get_model(name)
        fallback_id = model.create_fallback(fallback_name, description, answers)
        return {"status": "ok", "id": fallback_id}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_fallback(name: str, fallback_id: int, **kwargs) -> Dict:
    try:
        model = get_model(name)
        return model.get_fallback_by_id(fallback_id)
    except Exception as e:
        return {"error": str(e)}

def cmd_update_fallback(name: str, fallback_id: int, data: str, **kwargs) -> Dict:
    try:
        fallback_dict = json.loads(data)
        fallback_name = fallback_dict.get("name", "").strip()
        description = fallback_dict.get("description", "")
        answers = fallback_dict.get("answers", [])
        if not isinstance(answers, list) or not answers:
            return {"error": "At least one answer is required"}
        model = get_model(name)
        model.update_fallback(fallback_id, fallback_name, description, answers)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_fallback(name: str, fallback_id: int, **kwargs) -> Dict:
    try:
        model = get_model(name)
        model.delete_fallback(fallback_id)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_fallback_groups(name: str, fallback_id: int, **kwargs) -> Dict:
    try:
        model = get_model(name)
        groups = model.get_groups_by_fallback(fallback_id)
        nodes = model.get_nodes_by_fallback(fallback_id)
        return {"groups": groups, "nodes": nodes}
    except Exception as e:
        return {"error": str(e)}