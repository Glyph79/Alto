"""Commands for group and Q&A operations."""
import json
from typing import Dict
from train.model import get_model
from train.groups.utils import (
    load_followup_tree_skeleton,
    load_followup_tree_full,
    unpack_array,
    merge_followup_trees
)

def cmd_add_group(name: str, data: str, **kwargs) -> Dict:
    try:
        group_dict = json.loads(data)
        model = get_model(name)
        group_id = model.insert_group(group_dict)
        return {"status": "ok", "group_id": group_id}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_group(name: str, index: int, data: str, **kwargs) -> Dict:
    try:
        group_dict = json.loads(data)
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        model.update_group(group_id, group_dict)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_group(name: str, index: int, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        model.delete_group(group_id)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_followups(name: str, index: int, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        # Load skeleton only (for performance)
        tree = load_followup_tree_skeleton(model.conn, group_id)
        return tree
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_save_followups(name: str, index: int, data: str, **kwargs) -> Dict:
    try:
        incoming_tree = json.loads(data)
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]

        # Load current full tree from database
        current_tree = load_followup_tree_full(model.conn, group_id)

        # Merge incoming tree (which may have empty Q&A for unselected nodes) with current tree
        merged_tree = merge_followup_trees(current_tree, incoming_tree)

        # Update group with merged tree
        group = model.get_group_by_id(group_id, include_followups=False)  # don't load tree again
        group["follow_ups"] = merged_tree
        model.update_group(group_id, group)

        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_node_details(name: str, index: int, node_id: int, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        cur = model.conn.execute(
            "SELECT questions_blob, answers_blob FROM followup_nodes WHERE id = ? AND group_id = ?",
            (node_id, group_id)
        )
        row = cur.fetchone()
        if not row:
            return {"error": "Node not found"}
        return {
            "questions": unpack_array(row[0]),
            "answers": unpack_array(row[1])
        }
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

# ========== Lightweight group commands ==========
def cmd_get_group_summaries(name: str, **kwargs) -> Dict:
    """Return lightweight group summaries (no questions/answers/followups)."""
    try:
        model = get_model(name)
        summaries = model.get_group_summaries_with_counts()
        sections = model.get_sections()
        return {"groups": summaries, "sections": sections}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_group_full(name: str, index: int, **kwargs) -> Dict:
    """Return full group details (with questions, answers) but NOT the follow‑up tree."""
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        group = model.get_group_by_id(group_id, include_followups=False)
        del group["id"]  # frontend doesn't need internal id
        return group
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}