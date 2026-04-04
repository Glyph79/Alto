import os
import sys
import sqlite3
import shutil
import tempfile
from typing import Dict
from ..utils.file_helpers import (
    MODELS_BASE_DIR, find_model_dir, ensure_model_dir, safe_filename,
    pack_model, unpack_model, read_manifest, get_model_temp_dir
)
from ..model import get_model_info
from ..utils.delete_helpers import delete_with_retry
from ..model import _model_cache

def cmd_import_db(file: str, name: str = "", overwrite: bool = False, **kwargs) -> Dict:
    """Import a .db file, convert to .rbm container."""
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
            if final_name in _model_cache:
                print(f"[DEBUG] Closing cached model for '{final_name}'", file=sys.stderr)
                _model_cache[final_name].close_without_repack()
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
    safe = safe_filename(final_name)
    container_path = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.rbm")

    # Checkpoint the .db file to ensure no pending WAL
    conn = sqlite3.connect(file)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()

    # Read manifest and optionally update name
    conn = sqlite3.connect(file)
    manifest = get_model_info(conn)
    if final_name != manifest["name"]:
        conn.execute("UPDATE model_info SET name = ? WHERE name = ?", (final_name, manifest["name"]))
        conn.commit()
        manifest["name"] = final_name
    conn.close()

    # Pack into container
    fd, tmp_path = tempfile.mkstemp(suffix='.rbm', dir=os.path.dirname(container_path))
    os.close(fd)
    try:
        pack_model(file, manifest, tmp_path)
        os.replace(tmp_path, container_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return {"status": "ok", "model": manifest}

def cmd_import_rbm(file: str, name: str = "", overwrite: bool = False, **kwargs) -> Dict:
    """Import a .rbm container file directly."""
    print(f"[DEBUG] import-rbm called with file={file}, name='{name}', overwrite={overwrite}", file=sys.stderr)

    manifest = read_manifest(file)
    if not manifest:
        return {"error": "Uploaded file is not a valid Alto Trainer container (.rbm)"}
    db_name = manifest["name"]
    print(f"[DEBUG] Container internal name: '{db_name}'", file=sys.stderr)

    final_name = name if name else db_name
    print(f"[DEBUG] Final model name to use: '{final_name}'", file=sys.stderr)

    existing_dir = find_model_dir(final_name)
    if existing_dir is not None:
        print(f"[DEBUG] Model '{final_name}' already exists at {existing_dir}", file=sys.stderr)
        if overwrite:
            if final_name in _model_cache:
                print(f"[DEBUG] Closing cached model for '{final_name}'", file=sys.stderr)
                _model_cache[final_name].close_without_repack()
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
    safe = safe_filename(final_name)
    dest_container_path = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.rbm")

    if final_name != db_name:
        # Unpack, update DB name, repack
        temp_dir = get_model_temp_dir(final_name)
        db_path, old_manifest = unpack_model(file, temp_dir)
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE model_info SET name = ? WHERE name = ?", (final_name, db_name))
        conn.commit()
        new_manifest = get_model_info(conn)
        conn.close()
        fd, tmp_path = tempfile.mkstemp(suffix='.rbm', dir=os.path.dirname(dest_container_path))
        os.close(fd)
        try:
            pack_model(db_path, new_manifest, tmp_path)
            os.replace(tmp_path, dest_container_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        shutil.rmtree(temp_dir, ignore_errors=True)
        final_manifest = new_manifest
    else:
        # Copy container directly
        shutil.copy2(file, dest_container_path)
        final_manifest = manifest

    return {"status": "ok", "model": final_manifest}