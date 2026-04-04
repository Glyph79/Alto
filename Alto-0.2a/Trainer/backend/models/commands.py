import os
import sqlite3
import shutil
import tempfile
from typing import Optional, Dict, List
from ..utils.file_helpers import (
    MODELS_BASE_DIR, find_model_dir, ensure_model_dir,
    safe_filename, get_model_container_path, get_model_temp_dir,
    pack_model, unpack_model, read_manifest
)
from ..model import (
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
        for f in os.listdir(folder_path):
            if f.endswith('.rbm'):
                container_path = os.path.join(folder_path, f)
                manifest = read_manifest(container_path)
                if manifest:
                    models.append({"name": manifest["name"], "version": manifest["version"]})
                break
    return sorted(models, key=lambda x: x["name"])

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
        model = _model_cache.pop(name)
        model.close_without_repack()

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
    old_container = get_model_container_path(name)
    if not old_container:
        return {"error": f"Model '{name}' not found"}

    if find_model_dir(new_name) is not None:
        return {"error": f"Model '{new_name}' already exists"}

    if name in _model_cache:
        _model_cache[name].close_and_repack()
        del _model_cache[name]

    temp_dir = get_model_temp_dir(name)
    db_path, manifest = unpack_model(old_container, temp_dir)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE model_info SET name = ? WHERE name = ?", (new_name, name))
    conn.commit()
    new_manifest = get_model_info(conn)
    conn.close()

    old_folder = os.path.dirname(old_container)
    new_safe = safe_filename(new_name)
    new_container_path = os.path.join(old_folder, f"{new_safe}.rbm")

    fd, tmp_path = tempfile.mkstemp(suffix='.rbm', dir=old_folder)
    os.close(fd)
    try:
        pack_model(db_path, new_manifest, tmp_path)
        os.replace(tmp_path, new_container_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    os.remove(old_container)
    shutil.rmtree(temp_dir, ignore_errors=True)

    old_folder_path = os.path.join(MODELS_BASE_DIR, find_model_dir(name))
    new_folder_name = os.path.basename(old_folder_path).replace(safe_filename(name), new_safe, 1)
    new_folder_path = os.path.join(MODELS_BASE_DIR, new_folder_name)
    os.rename(old_folder_path, new_folder_path)

    return {"status": "ok", "old_name": name, "new_name": new_name}

def cmd_get_model_container_path(name: str, **kwargs) -> Dict:
    """
    Return the path to the .rbm container file for a model,
    ensuring it is up‑to‑date by flushing any cached changes.
    """
    if name in _model_cache:
        model = _model_cache.pop(name)
        model.close_and_repack()

    container_path = get_model_container_path(name)
    if not container_path or not os.path.isfile(container_path):
        return {"error": f"Model '{name}' not found or container missing"}
    return {"path": container_path}