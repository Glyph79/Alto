import json
from typing import Dict
from ..model import get_model
from ..schema.followups import (
    load_followup_tree_skeleton,
    load_followup_tree_full,
    merge_followup_trees
)
from ..utils.msgpack_helpers import unpack_array

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

        current_tree = load_followup_tree_full(model.conn, group_id)
        merged_tree = merge_followup_trees(current_tree, incoming_tree)

        group = model.get_group_by_id(group_id, include_followups=False)
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
            return {"error": f"Group index {index} out of range (0-{len(summaries)-1})"}
        group_id = summaries[index]["id"]
        cur = model.conn.execute(
            "SELECT questions_blob_id, answers_blob_id, fallback_id FROM followup_nodes WHERE id = ? AND group_id = ?",
            (node_id, group_id)
        )
        row = cur.fetchone()
        if not row:
            cur2 = model.conn.execute("SELECT id, group_id FROM followup_nodes WHERE id = ?", (node_id,))
            node_info = cur2.fetchone()
            if node_info:
                return {"error": f"Node {node_id} exists but belongs to group {node_info[1]}, not group {group_id}"}
            else:
                return {"error": f"Node {node_id} not found in any group"}
        fallback_name = ""
        if row[2]:
            fb_cur = model.conn.execute("SELECT name FROM fallbacks WHERE id = ?", (row[2],))
            fb_row = fb_cur.fetchone()
            if fb_row:
                fallback_name = fb_row[0]
        from ..schema.blob_utils import get_blob_data
        questions_raw = get_blob_data(model.conn, row[0])
        answers_raw = get_blob_data(model.conn, row[1])
        from ..utils.msgpack_helpers import unpack_array
        questions = unpack_array(questions_raw) if questions_raw else []
        answers = unpack_array(answers_raw) if answers_raw else []
        return {
            "questions": questions,
            "answers": answers,
            "fallback": fallback_name
        }
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_group_summaries(name: str, limit: int = 20, offset: int = 0, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries, total = model.get_group_summaries_with_counts(limit=limit, offset=offset)
        return {"groups": summaries, "total": total, "limit": limit, "offset": offset}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_group_full(name: str, index: int, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        # CHANGED: include_followups=True to preserve follow-up trees when editing
        group = model.get_group_by_id(group_id, include_followups=True)
        del group["id"]
        return group
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}