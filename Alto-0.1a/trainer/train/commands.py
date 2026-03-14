import os
import sys
import json
import datetime
import sqlite3
import shutil
from typing import Optional, Dict, List
from .core import (
    MODELS_BASE_DIR, find_model_dir, ensure_model_dir, get_model_db_path,
    delete_with_retry
)
from .model import (
    Model, get_model, close_all_models, init_model_db,
    get_model_info, update_model_info
)

# ----------------------------------------------------------------------
# Command handlers
# ----------------------------------------------------------------------
def cmd_list_models(**kwargs) -> List[Dict]:
    models = []
    if not os.path.exists(MODELS_BASE_DIR):
        return []
    for entry in os.listdir(MODELS_BASE_DIR):
        folder_path = os.path.join(MODELS_BASE_DIR, entry)
        if not os.path.isdir(folder_path):
            continue
        db_path = os.path.join(folder_path, "model.db")
        if not os.path.isfile(db_path):
            continue
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.execute("SELECT name, version FROM model_info")
            row = cur.fetchone()
            conn.close()
            if row:
                models.append({"name": row[0], "version": row[1]})
        except:
            pass
    return sorted(models, key=lambda x: x["name"])

def cmd_create_model(name: str, description: str = "", author: str = "", version: str = "1.0.0", **kwargs) -> Dict:
    if find_model_dir(name) is not None:
        return {"error": f"Model '{name}' already exists"}

    folder = ensure_model_dir(name)
    db_path = os.path.join(MODELS_BASE_DIR, folder, "model.db")
    conn = sqlite3.connect(db_path)
    try:
        init_model_db(conn, name, description, author, version)
    finally:
        conn.close()

    return {
        "status": "ok",
        "model": {
            "name": name,
            "description": description,
            "author": author,
            "version": version,
            "created_at": datetime.datetime.now().isoformat(),
            "updated_at": datetime.datetime.now().isoformat(),
            "sections": ["General", "Technical", "Creative"]
        }
    }

def cmd_get_model(name: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        info = get_model_info(model.conn)
        groups = model.get_all_groups_full()
        for g in groups:
            del g["id"]
        return {**info, "qa_groups": groups}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_model(name: str, description: Optional[str] = None, author: Optional[str] = None,
                     version: Optional[str] = None, **kwargs) -> Dict:
    try:
        model = get_model(name)
        updates = {}
        if description is not None:
            updates["description"] = description
        if author is not None:
            updates["author"] = author
        if version is not None:
            updates["version"] = version
        new_info = update_model_info(model.conn, **updates)
        return {"status": "ok", "model": new_info}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_model(name: str, **kwargs) -> Dict:
    if name in get_model.__globals__['_model_cache']:  # hacky, but we need to access cache
        # Better: have a function to close and remove from cache
        from .model import _model_cache
        if name in _model_cache:
            _model_cache[name].close()
            del _model_cache[name]

    folder = find_model_dir(name)
    if not folder:
        return {"error": f"Model '{name}' not found"}

    model_path = os.path.join(MODELS_BASE_DIR, folder)
    try:
        shutil.rmtree(model_path)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_rename_model(name: str, new_name: str, **kwargs) -> Dict:
    from .model import _model_cache
    from .core import safe_filename

    old_folder = find_model_dir(name)
    if not old_folder:
        return {"error": f"Model '{name}' not found"}

    if find_model_dir(new_name) is not None:
        return {"error": f"Model '{new_name}' already exists"}

    if name in _model_cache:
        _model_cache[name].close()
        del _model_cache[name]

    old_path = os.path.join(MODELS_BASE_DIR, old_folder)
    timestamp = old_folder.split('_')[0]
    safe_new = safe_filename(new_name)
    new_folder = f"{timestamp}_{safe_new}"
    new_path = os.path.join(MODELS_BASE_DIR, new_folder)

    counter = 1
    while os.path.exists(new_path):
        new_folder = f"{timestamp}_{safe_new}_{counter}"
        new_path = os.path.join(MODELS_BASE_DIR, new_folder)
        counter += 1

    try:
        os.rename(old_path, new_path)
        db_path = os.path.join(new_path, "model.db")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE model_info SET name = ? WHERE name = ?", (new_name, name))
        conn.commit()
        conn.close()
        return {"status": "ok", "old_name": name, "new_name": new_name}
    except Exception as e:
        if os.path.exists(new_path) and not os.path.exists(old_path):
            os.rename(new_path, old_path)
        return {"error": f"Rename failed: {str(e)}"}

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
        group = model.get_group_by_id(group_id)
        return group.get("follow_ups", [])
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_save_followups(name: str, index: int, data: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        summaries = model.get_group_summaries()
        if index < 0 or index >= len(summaries):
            return {"error": "Group index out of range"}
        group_id = summaries[index]["id"]
        group = model.get_group_by_id(group_id)
        group["follow_ups"] = json.loads(data)
        model.update_group(group_id, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_add_section(name: str, section: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        info = get_model_info(model.conn)
        if section in info["sections"]:
            return {"error": "Section already exists"}
        info["sections"].append(section)
        info["updated_at"] = datetime.datetime.now().isoformat()
        model.conn.execute(
            "UPDATE model_info SET sections = ?, updated_at = ? WHERE name = ?",
            (json.dumps(info["sections"], separators=(',', ':')), info["updated_at"], info["name"])
        )
        model.conn.commit()
        model._group_summaries = None
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_rename_section(name: str, old: str, new: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        conn = model.conn
        conn.execute("BEGIN IMMEDIATE")
        info = get_model_info(conn)
        if old not in info["sections"]:
            conn.rollback()
            return {"error": f"Section '{old}' not found"}
        if new in info["sections"] and new != old:
            conn.rollback()
            return {"error": f"Section '{new}' already exists"}
        idx = info["sections"].index(old)
        info["sections"][idx] = new
        info["updated_at"] = datetime.datetime.now().isoformat()
        conn.execute(
            "UPDATE model_info SET sections = ?, updated_at = ? WHERE name = ?",
            (json.dumps(info["sections"], separators=(',', ':')), info["updated_at"], info["name"])
        )
        cur = conn.execute("SELECT id FROM groups WHERE section = ?", (old,))
        for row in cur:
            conn.execute("UPDATE groups SET section = ? WHERE id = ?", (new, row[0]))
        conn.commit()
        model._group_summaries = None
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

def cmd_delete_section(name: str, section: str, action: str = "uncategorized",
                       target: Optional[str] = None, **kwargs) -> Dict:
    try:
        model = get_model(name)
        conn = model.conn
        conn.execute("BEGIN IMMEDIATE")
        info = get_model_info(conn)
        if section not in info["sections"]:
            conn.rollback()
            return {"error": f"Section '{section}' not found"}

        if action == "uncategorized":
            conn.execute("UPDATE groups SET section = '' WHERE section = ?", (section,))
        elif action == "move":
            if not target:
                conn.rollback()
                return {"error": "Target section required for move action"}
            if target not in info["sections"] and target != "":
                conn.rollback()
                return {"error": f"Target section '{target}' not found"}
            conn.execute("UPDATE groups SET section = ? WHERE section = ?", (target, section))
        elif action == "delete":
            cur = conn.execute("SELECT id FROM groups WHERE section = ?", (section,))
            for row in cur:
                from .model import delete_group as delete_group_op
                delete_group_op(conn, row[0])
        else:
            conn.rollback()
            return {"error": f"Invalid action: {action}"}

        info["sections"].remove(section)
        info["updated_at"] = datetime.datetime.now().isoformat()
        conn.execute(
            "UPDATE model_info SET sections = ?, updated_at = ? WHERE name = ?",
            (json.dumps(info["sections"], separators=(',', ':')), info["updated_at"], info["name"])
        )
        conn.commit()
        model._group_summaries = None
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

# ----------------------------------------------------------------------
# Import/Export commands
# ----------------------------------------------------------------------
def cmd_import_db(file: str, name: str = "", overwrite: bool = False, **kwargs) -> Dict:
    print(f"[DEBUG] import-db called with file={file}, name='{name}', overwrite={overwrite}", file=sys.stderr)

    try:
        conn = sqlite3.connect(file)
        cur = conn.execute("SELECT name FROM model_info")
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"error": "Uploaded file is not a valid Alto Trainer database"}
        db_name = row[0]
        conn.close()
        print(f"[DEBUG] Database internal name: '{db_name}'", file=sys.stderr)
    except Exception as e:
        return {"error": f"Could not read database: {str(e)}"}

    final_name = name if name else db_name
    print(f"[DEBUG] Final model name to use: '{final_name}'", file=sys.stderr)

    existing_dir = find_model_dir(final_name)
    if existing_dir is not None:
        print(f"[DEBUG] Model '{final_name}' already exists at {existing_dir}", file=sys.stderr)
        if overwrite:
            from .model import _model_cache
            if final_name in _model_cache:
                print(f"[DEBUG] Closing cached model for '{final_name}'", file=sys.stderr)
                _model_cache[final_name].close()
                del _model_cache[final_name]
            old_path = os.path.join(MODELS_BASE_DIR, existing_dir)
            try:
                delete_with_retry(old_path)
                print(f"[DEBUG] Successfully deleted old model folder: {old_path}", file=sys.stderr)
            except Exception as e:
                return {"error": f"Could not delete existing model: {str(e)}"}
        else:
            print(f"[DEBUG] Returning conflict for '{final_name}'", file=sys.stderr)
            return {
                "error": f"Model '{final_name}' already exists",
                "code": "CONFLICT",
                "existing_name": final_name,
                "db_name": db_name
            }
    else:
        print(f"[DEBUG] No existing model found for '{final_name}'", file=sys.stderr)

    folder = ensure_model_dir(final_name)
    dest_path = os.path.join(MODELS_BASE_DIR, folder, "model.db")
    print(f"[DEBUG] Creating new model at {dest_path}", file=sys.stderr)

    try:
        shutil.copyfile(file, dest_path)
        if final_name != db_name:
            print(f"[DEBUG] Updating database name from '{db_name}' to '{final_name}'", file=sys.stderr)
            conn = sqlite3.connect(dest_path)
            conn.execute("UPDATE model_info SET name = ? WHERE name = ?", (final_name, db_name))
            conn.commit()
            conn.close()

        conn = sqlite3.connect(dest_path)
        info = get_model_info(conn)
        conn.close()
        print(f"[DEBUG] Import successful for '{final_name}'", file=sys.stderr)
        return {"status": "ok", "model": info}
    except Exception as e:
        shutil.rmtree(os.path.join(MODELS_BASE_DIR, folder), ignore_errors=True)
        print(f"[DEBUG] Import failed: {str(e)}", file=sys.stderr)
        return {"error": f"Failed to import database: {str(e)}"}

def cmd_get_model_db_path(name: str, **kwargs) -> Dict:
    folder = find_model_dir(name)
    if not folder:
        return {"error": f"Model '{name}' not found"}
    db_path = os.path.join(MODELS_BASE_DIR, folder, "model.db")
    if not os.path.isfile(db_path):
        return {"error": "Database file missing"}
    return {"path": os.path.abspath(db_path)}

# ----------------------------------------------------------------------
# Command registry
# ----------------------------------------------------------------------
COMMANDS = {
    "list-models":      cmd_list_models,
    "create-model":     cmd_create_model,
    "get-model":        cmd_get_model,
    "update-model":     cmd_update_model,
    "delete-model":     cmd_delete_model,
    "rename-model":     cmd_rename_model,
    "add-group":        cmd_add_group,
    "update-group":     cmd_update_group,
    "delete-group":     cmd_delete_group,
    "add-question":     cmd_add_question,
    "update-question":  cmd_update_question,
    "delete-question":  cmd_delete_question,
    "add-answer":       cmd_add_answer,
    "update-answer":    cmd_update_answer,
    "delete-answer":    cmd_delete_answer,
    "get-followups":    cmd_get_followups,
    "save-followups":   cmd_save_followups,
    "add-section":      cmd_add_section,
    "rename-section":   cmd_rename_section,
    "delete-section":   cmd_delete_section,
    "get-model-db-path": cmd_get_model_db_path,
    "import-db":        cmd_import_db,
}