"""Commands for group and Q&A operations."""
import json
from typing import Dict
from ..model import get_model
from ..core import load_followup_tree_skeleton, unpack_array

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

def cmd_add_question(name: str, index: int, text: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        group = model.get_group_by_id(group_id)
        group["questions"].append(text)
        model.update_group(group_id, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_question(name: str, index: int, qidx: int, text: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        group = model.get_group_by_id(group_id)
        if qidx < 0 or qidx >= len(group["questions"]):
            return {"error": "Question index out of range"}
        group["questions"][qidx] = text
        model.update_group(group_id, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_question(name: str, index: int, qidx: int, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        group = model.get_group_by_id(group_id)
        if qidx < 0 or qidx >= len(group["questions"]):
            return {"error": "Question index out of range"}
        del group["questions"][qidx]
        model.update_group(group_id, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_add_answer(name: str, index: int, text: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        group = model.get_group_by_id(group_id)
        group["answers"].append(text)
        model.update_group(group_id, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_answer(name: str, index: int, aidx: int, text: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        group = model.get_group_by_id(group_id)
        if aidx < 0 or aidx >= len(group["answers"]):
            return {"error": "Answer index out of range"}
        group["answers"][aidx] = text
        model.update_group(group_id, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_answer(name: str, index: int, aidx: int, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        group = model.get_group_by_id(group_id)
        if aidx < 0 or aidx >= len(group["answers"]):
            return {"error": "Answer index out of range"}
        del group["answers"][aidx]
        model.update_group(group_id, group)
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
        # Load skeleton only
        tree = load_followup_tree_skeleton(model.conn, group_id)
        return tree
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_save_followups(name: str, index: int, data: str, **kwargs) -> Dict:
    try:
        group_dict = json.loads(data)
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        group = model.get_group_by_id(group_id)
        group["follow_ups"] = group_dict
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

# ========== New lightweight commands ==========
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
    """Return full group details (with questions, answers, followups) by index."""
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        group = model.get_group_by_id(group_id)
        del group["id"]  # frontend doesn't need internal id
        return group
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}