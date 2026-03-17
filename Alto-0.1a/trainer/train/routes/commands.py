"""Commands for route management."""
import json
from typing import Dict, List
from train.model import get_model

def cmd_get_route_summaries(name: str, **kwargs) -> List[Dict]:
    """Return list of {id, module_name, variant_count}."""
    try:
        model = get_model(name)
        return model.get_route_summaries()
    except Exception as e:
        return {"error": str(e)}

def cmd_get_route_full(name: str, index: int, **kwargs) -> Dict:
    """Return full route details (module_name, variants)."""
    try:
        model = get_model(name)
        return model.get_route_full(index)
    except IndexError:
        return {"error": "Route index out of range"}
    except Exception as e:
        return {"error": str(e)}

def cmd_add_route(name: str, data: str, **kwargs) -> Dict:
    """Add a new route. Data must contain 'module_name' and 'variants' (list)."""
    try:
        data_dict = json.loads(data)
        module_name = data_dict.get("module_name")
        variants = data_dict.get("variants", [])
        if not module_name:
            return {"error": "Module name required"}
        if not isinstance(variants, list) or not variants:
            return {"error": "Variants must be a non‑empty list"}

        model = get_model(name)
        route_id = model.add_route(module_name, variants)
        return {"status": "ok", "id": route_id}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_route(name: str, index: int, data: str, **kwargs) -> Dict:
    """Update an existing route."""
    try:
        data_dict = json.loads(data)
        module_name = data_dict.get("module_name")
        variants = data_dict.get("variants", [])
        if not module_name:
            return {"error": "Module name required"}
        if not isinstance(variants, list) or not variants:
            return {"error": "Variants must be a non‑empty list"}

        model = get_model(name)
        model.update_route(index, module_name, variants)
        return {"status": "ok"}
    except IndexError:
        return {"error": "Route index out of range"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_route(name: str, index: int, **kwargs) -> Dict:
    """Delete a route by index."""
    try:
        model = get_model(name)
        model.delete_route(index)
        return {"status": "ok"}
    except IndexError:
        return {"error": "Route index out of range"}
    except Exception as e:
        return {"error": str(e)}