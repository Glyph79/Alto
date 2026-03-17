"""Commands for route management."""
import json
from typing import Dict, List
from train.utils.routes_helpers import (
    get_route_summaries, get_route_full,
    add_route, update_route, delete_route
)

# Note: 'name' parameter is kept for CLI compatibility but ignored.
def cmd_get_route_summaries(name: str = None, **kwargs) -> List[Dict]:
    """Return list of {id, module_name, variant_count}."""
    try:
        return get_route_summaries()
    except Exception as e:
        return {"error": str(e)}

def cmd_get_route_full(name: str, index: int, **kwargs) -> Dict:
    """Return full route details (module_name, variants) by index (order by id)."""
    try:
        summaries = get_route_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Route index out of range"}
        route_id = summaries[index]["id"]
        return get_route_full(route_id)
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

        route_id = add_route(module_name, variants)
        return {"status": "ok", "id": route_id}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_route(name: str, index: int, data: str, **kwargs) -> Dict:
    """Update an existing route by index."""
    try:
        data_dict = json.loads(data)
        module_name = data_dict.get("module_name")
        variants = data_dict.get("variants", [])
        if not module_name:
            return {"error": "Module name required"}
        if not isinstance(variants, list) or not variants:
            return {"error": "Variants must be a non‑empty list"}

        summaries = get_route_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Route index out of range"}
        route_id = summaries[index]["id"]
        update_route(route_id, module_name, variants)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_route(name: str, index: int, **kwargs) -> Dict:
    """Delete a route by index."""
    try:
        summaries = get_route_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Route index out of range"}
        route_id = summaries[index]["id"]
        delete_route(route_id)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}