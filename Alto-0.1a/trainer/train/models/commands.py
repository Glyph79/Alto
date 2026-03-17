"""Commands for model CRUD, rename, list, and path retrieval."""
import os
import datetime
import sqlite3
import shutil
from typing import Optional, Dict, List
from train.utils.file_helpers import (
    MODELS_BASE_DIR, find_model_dir, ensure_model_dir, get_model_db_path,
    safe_filename
)
from train.model import (
    Model, get_model, _model_cache, init_model_db,
    get_model_info, update_model_info
)

def cmd_list_models(**kwargs) -> List[Dict]:
    models = []
    if not os.path.exists(MODELS_BASE_DIR):
        return []
    for entry in os.listdir(MODELS_BASE_DIR):
        folder_path = os.path.join(MODELS_BASE_DIR, entry)
        if not os.path.isdir(folder_path):
            continue
        db_files = [f for f in os.listdir(folder_path) if f.endswith('.db')]
        if not db_files:
            continue
        db_path = os.path.join(folder_path, db_files[0])
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
    safe = safe_filename(name)
    db_path = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.db")
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
            "sections": ["General", "Technical", "Creative"],
            "topics": ["general", "greeting", "programming", "ai", "gaming", "creative", "thanks"]
        }
    }

def cmd_get_model(name: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        info = get_model_info(model.conn)
        return info
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
        old_safe = safe_filename(name)
        new_safe = safe_filename(new_name)
        old_db_path = os.path.join(new_path, f"{old_safe}.db")
        new_db_path = os.path.join(new_path, f"{new_safe}.db")
        if os.path.exists(old_db_path):
            os.rename(old_db_path, new_db_path)
        else:
            old_model_db = os.path.join(new_path, "model.db")
            if os.path.exists(old_model_db):
                os.rename(old_model_db, new_db_path)

        conn = sqlite3.connect(new_db_path)
        conn.execute("UPDATE model_info SET name = ? WHERE name = ?", (new_name, name))
        conn.commit()
        conn.close()
        return {"status": "ok", "old_name": name, "new_name": new_name}
    except Exception as e:
        if os.path.exists(new_path) and not os.path.exists(old_path):
            os.rename(new_path, old_path)
        return {"error": f"Rename failed: {str(e)}"}

def cmd_get_model_db_path(name: str, **kwargs) -> Dict:
    folder = find_model_dir(name)
    if not folder:
        return {"error": f"Model '{name}' not found"}
    db_path = get_model_db_path(name)
    if not db_path or not os.path.isfile(db_path):
        return {"error": "Database file missing"}
    return {"path": os.path.abspath(db_path)}