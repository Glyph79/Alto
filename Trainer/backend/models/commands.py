import os
import sqlite3
import shutil
import tempfile
import datetime
from typing import Optional, Dict, List
from ..utils.file_helpers import (
    MODELS_BASE_DIR, find_model_dir, ensure_model_dir,
    safe_filename, get_model_container_path, get_model_temp_dir,
    pack_model, unpack_model, read_manifest, list_all_models, find_all_model_dirs
)
from ..model import (
    Model, get_model, _model_cache, init_model_db,
    get_model_info, update_model_info
)

def cmd_list_models(**kwargs) -> List[Dict]:
    return list_all_models()

def cmd_create_model(name: str, description: str = "", author: str = "", version: str = "1.0.0", **kwargs) -> Dict:
    if find_model_dir(name) is not None:
        return {"error": f"Model '{name}' already exists"}

    folder = ensure_model_dir(name)
    safe = safe_filename(name)
    container_path = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.rbm")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "database.db")
        conn = sqlite3.connect(db_path)
        init_model_db(conn, name, description, author, version)
        conn.close()
        conn = sqlite3.connect(db_path)
        manifest = get_model_info(conn)
        conn.close()
        fd, tmp_path = tempfile.mkstemp(suffix='.rbm', dir=os.path.dirname(container_path))
        os.close(fd)
        try:
            pack_model(db_path, manifest, tmp_path)
            os.replace(tmp_path, container_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    return {"status": "ok", "model": manifest}

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
        _model_cache[name].close_without_repack()
        del _model_cache[name]

    for dir_name, model_name in find_all_model_dirs():
        if model_name == name:
            model_path = os.path.join(MODELS_BASE_DIR, dir_name)
            try:
                shutil.rmtree(model_path)
                return {"status": "ok"}
            except Exception as e:
                return {"error": str(e)}
    return {"error": f"Model '{name}' not found"}

def cmd_rename_model(name: str, new_name: str, **kwargs) -> Dict:
    container_path = get_model_container_path(name)
    if not container_path:
        return {"error": f"Model '{name}' not found"}

    if name != new_name and find_model_dir(new_name) is not None:
        return {"error": f"Model '{new_name}' already exists"}

    if name in _model_cache:
        _model_cache[name].close_and_repack()
        del _model_cache[name]

    temp_dir = get_model_temp_dir(name)
    db_path, manifest = unpack_model(container_path, temp_dir)
    if manifest["name"] != name:
        return {"error": f"Internal mismatch: manifest name '{manifest['name']}' != '{name}'"}
    manifest["name"] = new_name
    manifest["updated_at"] = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE model_info SET name = ?, updated_at = ? WHERE name = ?", (new_name, manifest["updated_at"], name))
    conn.commit()
    conn.close()
    fd, tmp_path = tempfile.mkstemp(suffix='.rbm', dir=os.path.dirname(container_path))
    os.close(fd)
    try:
        pack_model(db_path, manifest, tmp_path)
        os.replace(tmp_path, container_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    shutil.rmtree(temp_dir, ignore_errors=True)
    return {"status": "ok", "old_name": name, "new_name": new_name}

def cmd_get_model_container_path(name: str, **kwargs) -> Dict:
    if name in _model_cache:
        model = _model_cache.pop(name)
        model.close_and_repack()
    container_path = get_model_container_path(name)
    if not container_path or not os.path.isfile(container_path):
        return {"error": f"Model '{name}' not found or container missing"}
    return {"path": container_path}