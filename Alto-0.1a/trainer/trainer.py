#!/usr/bin/env python3
"""
Alto Trainer – per‑model SQLite backend with MessagePack BLOBs and word index.
Each model is stored in models/<timestamp>_<safe_name>/model.db.
No central registry – folder scanning is used.
"""

import argparse
import json
import os
import sys
import datetime
import sqlite3
import shutil
import msgpack
import re
import time  # added for retry delays and debugging
from typing import Any, Dict, List, Optional

MODELS_BASE_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_BASE_DIR, exist_ok=True)

_model_connection_cache: Dict[str, sqlite3.Connection] = {}

def _safe_filename(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)

def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")

def _find_model_dir(model_name: str) -> Optional[str]:
    safe = _safe_filename(model_name)
    if not os.path.exists(MODELS_BASE_DIR):
        return None
    for entry in os.listdir(MODELS_BASE_DIR):
        full_path = os.path.join(MODELS_BASE_DIR, entry)
        if not os.path.isdir(full_path):
            continue
        if entry.endswith('_' + safe):
            return entry
    return None

def _ensure_model_dir(model_name: str) -> str:
    safe = _safe_filename(model_name)
    base = f"{_timestamp()}_{safe}"
    candidate = base
    counter = 1
    while os.path.exists(os.path.join(MODELS_BASE_DIR, candidate)):
        candidate = f"{base}_{counter}"
        counter += 1
    full_path = os.path.join(MODELS_BASE_DIR, candidate)
    os.makedirs(full_path, exist_ok=True)
    return candidate

def _get_model_db_path(model_name: str) -> Optional[str]:
    folder = _find_model_dir(model_name)
    if not folder:
        return None
    return os.path.join(MODELS_BASE_DIR, folder, "model.db")

def _connect_model_db(model_name: str, use_cache: bool = False) -> sqlite3.Connection:
    if use_cache and model_name in _model_connection_cache:
        return _model_connection_cache[model_name]

    db_path = _get_model_db_path(model_name)
    if db_path is None:
        raise FileNotFoundError(f"Model '{model_name}' not found")

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -20000")
    conn.execute("PRAGMA mmap_size = 30000000000")
    conn.execute("PRAGMA foreign_keys = ON")

    if use_cache:
        _model_connection_cache[model_name] = conn
    return conn

def _close_all_model_connections():
    for conn in _model_connection_cache.values():
        conn.close()
    _model_connection_cache.clear()

# ----------------------------------------------------------------------
# Word index helpers
# ----------------------------------------------------------------------
def _normalize_word(word: str) -> str:
    return re.sub(r'[^\w\s]', '', word.lower())

def _update_word_index(conn: sqlite3.Connection, group_id: int, questions: List[str]):
    conn.execute("DELETE FROM word_index WHERE group_id = ?", (group_id,))
    for q_idx, question in enumerate(questions):
        words = question.split()
        for word in words:
            norm = _normalize_word(word)
            if not norm:
                continue
            cur = conn.execute("INSERT OR IGNORE INTO words (word) VALUES (?)", (norm,))
            cur = conn.execute("SELECT id FROM words WHERE word = ?", (norm,))
            word_id = cur.fetchone()[0]
            conn.execute(
                "INSERT INTO word_index (word_id, group_id, question_idx) VALUES (?, ?, ?)",
                (word_id, group_id, q_idx)
            )

# ----------------------------------------------------------------------
# MsgPack helpers
# ----------------------------------------------------------------------
def _pack_array(arr: List) -> bytes:
    return msgpack.packb(arr, use_bin_type=True)

def _unpack_array(data: bytes) -> List:
    return msgpack.unpackb(data, raw=False)

# ----------------------------------------------------------------------
# Model DB initialization and queries
# ----------------------------------------------------------------------
def _init_model_db(conn: sqlite3.Connection, model_name: str, description: str, author: str, version: str):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_info (
            name TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            author TEXT NOT NULL,
            version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sections TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            topic TEXT NOT NULL,
            priority TEXT NOT NULL,
            section TEXT NOT NULL,
            questions_blob BLOB NOT NULL,
            answers_blob BLOB NOT NULL,
            follow_ups_blob BLOB NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS word_index (
            word_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            question_idx INTEGER NOT NULL,
            FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_section ON groups(section)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_topic ON groups(topic)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_priority ON groups(priority)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_word ON words(word)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_word_index_word_id ON word_index(word_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_word_index_group_id ON word_index(group_id)")

    now = datetime.datetime.now().isoformat()
    sections = json.dumps(["General", "Technical", "Creative"], separators=(',', ':'))
    conn.execute(
        """INSERT INTO model_info
           (name, description, author, version, created_at, updated_at, sections)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (model_name, description, author, version, now, now, sections)
    )
    conn.commit()

def _get_model_info(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.execute("SELECT name, description, author, version, created_at, updated_at, sections FROM model_info")
    row = cur.fetchone()
    if not row:
        raise ValueError("Model info not found")
    return {
        "name": row[0],
        "description": row[1],
        "author": row[2],
        "version": row[3],
        "created_at": row[4],
        "updated_at": row[5],
        "sections": json.loads(row[6])
    }

def _update_model_info(conn: sqlite3.Connection, **kwargs):
    info = _get_model_info(conn)
    if "description" in kwargs:
        info["description"] = kwargs["description"]
    if "author" in kwargs:
        info["author"] = kwargs["author"]
    if "version" in kwargs:
        info["version"] = kwargs["version"]
    info["updated_at"] = datetime.datetime.now().isoformat()
    conn.execute(
        """UPDATE model_info
           SET description = ?, author = ?, version = ?, updated_at = ?, sections = ?
           WHERE name = ?""",
        (info["description"], info["author"], info["version"],
         info["updated_at"], json.dumps(info["sections"], separators=(',', ':')), info["name"])
    )
    conn.commit()
    return info

# ----------------------------------------------------------------------
# Group operations with explicit transactions
# ----------------------------------------------------------------------
def _group_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row[0],
        "group_name": row[1],
        "topic": row[2],
        "priority": row[3],
        "section": row[4],
        "questions": _unpack_array(row[5]),
        "answers": _unpack_array(row[6]),
        "follow_ups": _unpack_array(row[7])
    }

def _get_all_groups(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    cur = conn.execute(
        "SELECT id, group_name, topic, priority, section, questions_blob, answers_blob, follow_ups_blob FROM groups ORDER BY id"
    )
    return [_group_from_row(row) for row in cur]

def _get_group_by_index(conn: sqlite3.Connection, index: int) -> Dict[str, Any]:
    groups = _get_all_groups(conn)
    if index < 0 or index >= len(groups):
        raise IndexError("Group index out of range")
    return groups[index]

def _insert_group(conn: sqlite3.Connection, model_name: str, group_dict: Dict[str, Any]) -> int:
    group_dict.setdefault("group_name", "New Group")
    group_dict.setdefault("questions", [])
    group_dict.setdefault("answers", [])
    group_dict.setdefault("topic", "general")
    group_dict.setdefault("priority", "medium")
    group_dict.setdefault("section", "")
    group_dict.setdefault("follow_ups", [])

    questions_blob = _pack_array(group_dict["questions"])
    answers_blob = _pack_array(group_dict["answers"])
    follow_ups_blob = _pack_array(group_dict["follow_ups"])

    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """INSERT INTO groups (group_name, topic, priority, section, questions_blob, answers_blob, follow_ups_blob)
               VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (group_dict["group_name"], group_dict["topic"], group_dict["priority"],
             group_dict["section"], questions_blob, answers_blob, follow_ups_blob)
        )
        group_id = cursor.fetchone()[0]
        _update_word_index(conn, group_id, group_dict["questions"])
        conn.commit()
        return group_id
    except Exception:
        conn.rollback()
        raise

def _update_group(conn: sqlite3.Connection, group_id: int, group_dict: Dict[str, Any]):
    group_dict.setdefault("group_name", "New Group")
    group_dict.setdefault("questions", [])
    group_dict.setdefault("answers", [])
    group_dict.setdefault("topic", "general")
    group_dict.setdefault("priority", "medium")
    group_dict.setdefault("section", "")
    group_dict.setdefault("follow_ups", [])

    questions_blob = _pack_array(group_dict["questions"])
    answers_blob = _pack_array(group_dict["answers"])
    follow_ups_blob = _pack_array(group_dict["follow_ups"])

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """UPDATE groups SET group_name = ?, topic = ?, priority = ?, section = ?,
               questions_blob = ?, answers_blob = ?, follow_ups_blob = ? WHERE id = ?""",
            (group_dict["group_name"], group_dict["topic"], group_dict["priority"],
             group_dict["section"], questions_blob, answers_blob, follow_ups_blob, group_id)
        )
        _update_word_index(conn, group_id, group_dict["questions"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def _delete_group(conn: sqlite3.Connection, group_id: int):
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def _update_group_by_index(conn: sqlite3.Connection, index: int, new_data: Dict[str, Any]):
    group = _get_group_by_index(conn, index)
    group_id = group["id"]
    _update_group(conn, group_id, new_data)

def _delete_group_by_index(conn: sqlite3.Connection, index: int):
    group = _get_group_by_index(conn, index)
    group_id = group["id"]
    _delete_group(conn, group_id)

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
    if _find_model_dir(name) is not None:
        return {"error": f"Model '{name}' already exists"}

    folder = _ensure_model_dir(name)
    db_path = os.path.join(MODELS_BASE_DIR, folder, "model.db")
    conn = sqlite3.connect(db_path)
    try:
        _init_model_db(conn, name, description, author, version)
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
        conn = _connect_model_db(name, use_cache=False)
        info = _get_model_info(conn)
        groups = _get_all_groups(conn)
        for g in groups:
            del g["id"]
        return {**info, "qa_groups": groups}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_update_model(name: str, description: Optional[str] = None, author: Optional[str] = None,
                     version: Optional[str] = None, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        updates = {}
        if description is not None:
            updates["description"] = description
        if author is not None:
            updates["author"] = author
        if version is not None:
            updates["version"] = version
        new_info = _update_model_info(conn, **updates)
        return {"status": "ok", "model": new_info}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_delete_model(name: str, **kwargs) -> Dict:
    if name in _model_connection_cache:
        _model_connection_cache[name].close()
        del _model_connection_cache[name]

    folder = _find_model_dir(name)
    if not folder:
        return {"error": f"Model '{name}' not found"}

    model_path = os.path.join(MODELS_BASE_DIR, folder)
    try:
        shutil.rmtree(model_path)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_add_group(name: str, data: str, **kwargs) -> Dict:
    try:
        group_dict = json.loads(data)
        conn = _connect_model_db(name, use_cache=False)
        group_id = _insert_group(conn, name, group_dict)
        return {"status": "ok", "group_id": group_id}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_update_group(name: str, index: int, data: str, **kwargs) -> Dict:
    try:
        group_dict = json.loads(data)
        conn = _connect_model_db(name, use_cache=False)
        _update_group_by_index(conn, index, group_dict)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except IndexError:
        return {"error": "Group index out of range"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_delete_group(name: str, index: int, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        _delete_group_by_index(conn, index)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except IndexError:
        return {"error": "Group index out of range"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_add_question(name: str, index: int, text: str, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        group = _get_group_by_index(conn, index)
        group["questions"].append(text)
        _update_group_by_index(conn, index, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_update_question(name: str, index: int, qidx: int, text: str, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        group = _get_group_by_index(conn, index)
        if qidx < 0 or qidx >= len(group["questions"]):
            return {"error": "Question index out of range"}
        group["questions"][qidx] = text
        _update_group_by_index(conn, index, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_delete_question(name: str, index: int, qidx: int, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        group = _get_group_by_index(conn, index)
        if qidx < 0 or qidx >= len(group["questions"]):
            return {"error": "Question index out of range"}
        del group["questions"][qidx]
        _update_group_by_index(conn, index, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_add_answer(name: str, index: int, text: str, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        group = _get_group_by_index(conn, index)
        group["answers"].append(text)
        _update_group_by_index(conn, index, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_update_answer(name: str, index: int, aidx: int, text: str, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        group = _get_group_by_index(conn, index)
        if aidx < 0 or aidx >= len(group["answers"]):
            return {"error": "Answer index out of range"}
        group["answers"][aidx] = text
        _update_group_by_index(conn, index, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_delete_answer(name: str, index: int, aidx: int, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        group = _get_group_by_index(conn, index)
        if aidx < 0 or aidx >= len(group["answers"]):
            return {"error": "Answer index out of range"}
        del group["answers"][aidx]
        _update_group_by_index(conn, index, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_get_followups(name: str, index: int, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        group = _get_group_by_index(conn, index)
        return group.get("follow_ups", [])
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_save_followups(name: str, index: int, data: str, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        group = _get_group_by_index(conn, index)
        group["follow_ups"] = json.loads(data)
        _update_group_by_index(conn, index, group)
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_add_section(name: str, section: str, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        info = _get_model_info(conn)
        if section in info["sections"]:
            return {"error": "Section already exists"}
        info["sections"].append(section)
        info["updated_at"] = datetime.datetime.now().isoformat()
        conn.execute(
            "UPDATE model_info SET sections = ?, updated_at = ? WHERE name = ?",
            (json.dumps(info["sections"], separators=(',', ':')), info["updated_at"], info["name"])
        )
        conn.commit()
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_rename_section(name: str, old: str, new: str, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        conn.execute("BEGIN IMMEDIATE")
        info = _get_model_info(conn)
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
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_delete_section(name: str, section: str, action: str = "uncategorized",
                       target: Optional[str] = None, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        conn.execute("BEGIN IMMEDIATE")
        info = _get_model_info(conn)
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
                _delete_group(conn, row[0])
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
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()

# ----------------------------------------------------------------------
# Import helper with retry
# ----------------------------------------------------------------------
def delete_with_retry(path, max_attempts=5, delay=0.1):
    """Attempt to delete a directory, retrying with exponential backoff."""
    for attempt in range(max_attempts):
        try:
            shutil.rmtree(path)
            return True
        except Exception as e:
            if attempt == max_attempts - 1:
                raise  # final attempt failed
            time.sleep(delay * (2 ** attempt))  # backoff
    return False

def cmd_import_db(file: str, name: str = "", overwrite: bool = False, **kwargs) -> Dict:
    """
    Import a .db file as a new model.
    - Reads the name from the database.
    - If `name` is provided, that overrides the database's internal name.
    - If a model with the final name exists and overwrite=True, it is deleted first.
    - Otherwise, if it exists, a conflict is returned.
    """
    # Debug: log received parameters
    print(f"[DEBUG] import-db called with file={file}, name='{name}', overwrite={overwrite}", file=sys.stderr)

    try:
        # Read the name from the uploaded db
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

    # Check if a model with that name already exists
    existing_dir = _find_model_dir(final_name)
    if existing_dir is not None:
        print(f"[DEBUG] Model '{final_name}' already exists at {existing_dir}", file=sys.stderr)
        if overwrite:
            # Close any cached connection first
            if final_name in _model_connection_cache:
                print(f"[DEBUG] Closing cached connection for '{final_name}'", file=sys.stderr)
                _model_connection_cache[final_name].close()
                del _model_connection_cache[final_name]

            # Delete the existing model with retry (Windows file locking)
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

    # Create new model directory
    folder = _ensure_model_dir(final_name)
    dest_path = os.path.join(MODELS_BASE_DIR, folder, "model.db")
    print(f"[DEBUG] Creating new model at {dest_path}", file=sys.stderr)

    try:
        shutil.copyfile(file, dest_path)
        # If the name in the db differs from final_name, update it
        if final_name != db_name:
            print(f"[DEBUG] Updating database name from '{db_name}' to '{final_name}'", file=sys.stderr)
            conn = sqlite3.connect(dest_path)
            conn.execute("UPDATE model_info SET name = ? WHERE name = ?", (final_name, db_name))
            conn.commit()
            conn.close()

        # Read the model info to return
        conn = sqlite3.connect(dest_path)
        info = _get_model_info(conn)
        conn.close()
        print(f"[DEBUG] Import successful for '{final_name}'", file=sys.stderr)
        return {"status": "ok", "model": info}
    except Exception as e:
        # Clean up on error
        shutil.rmtree(os.path.join(MODELS_BASE_DIR, folder), ignore_errors=True)
        print(f"[DEBUG] Import failed: {str(e)}", file=sys.stderr)
        return {"error": f"Failed to import database: {str(e)}"}

# ----------------------------------------------------------------------
# Utility command to get db path
# ----------------------------------------------------------------------
def cmd_get_model_db_path(name: str, **kwargs) -> Dict:
    folder = _find_model_dir(name)
    if not folder:
        return {"error": f"Model '{name}' not found"}
    db_path = os.path.join(MODELS_BASE_DIR, folder, "model.db")
    if not os.path.isfile(db_path):
        return {"error": "Database file missing"}
    return {"path": os.path.abspath(db_path)}

COMMANDS = {
    "list-models":      cmd_list_models,
    "create-model":     cmd_create_model,
    "get-model":        cmd_get_model,
    "update-model":     cmd_update_model,
    "delete-model":     cmd_delete_model,
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

def interactive_loop():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line or line == "exit":
            break
        try:
            req = json.loads(line)
            cmd = req.get("command")
            kwargs = req.get("args", {})
            if cmd not in COMMANDS:
                result = {"error": f"Unknown command: {cmd}"}
            else:
                model_name = kwargs.get("name")
                if model_name and cmd not in ("list-models", "create-model", "import-db", "get-model-db-path"):
                    _connect_model_db(model_name, use_cache=True)
                result = COMMANDS[cmd](**kwargs)
        except FileNotFoundError as e:
            result = {"error": str(e)}
        except Exception as e:
            result = {"error": str(e)}
        print(json.dumps(result), flush=True)
    _close_all_model_connections()

def main():
    if "--interactive" in sys.argv:
        interactive_loop()
        return

    parser = argparse.ArgumentParser(description="Alto Trainer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("list-models")
    p.set_defaults(func=cmd_list_models)

    p = subparsers.add_parser("create-model")
    p.add_argument("name")
    p.add_argument("--description", default="")
    p.add_argument("--author", default="")
    p.add_argument("--version", default="1.0.0")
    p.set_defaults(func=cmd_create_model)

    p = subparsers.add_parser("get-model")
    p.add_argument("name")
    p.set_defaults(func=cmd_get_model)

    p = subparsers.add_parser("update-model")
    p.add_argument("name")
    p.add_argument("--description")
    p.add_argument("--author")
    p.add_argument("--version")
    p.set_defaults(func=cmd_update_model)

    p = subparsers.add_parser("delete-model")
    p.add_argument("name")
    p.set_defaults(func=cmd_delete_model)

    p = subparsers.add_parser("add-group")
    p.add_argument("name")
    p.add_argument("--data", required=True)
    p.set_defaults(func=cmd_add_group)

    p = subparsers.add_parser("update-group")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("--data", required=True)
    p.set_defaults(func=cmd_update_group)

    p = subparsers.add_parser("delete-group")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.set_defaults(func=cmd_delete_group)

    p = subparsers.add_parser("add-question")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_add_question)

    p = subparsers.add_parser("update-question")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("qidx", type=int)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_update_question)

    p = subparsers.add_parser("delete-question")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("qidx", type=int)
    p.set_defaults(func=cmd_delete_question)

    p = subparsers.add_parser("add-answer")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_add_answer)

    p = subparsers.add_parser("update-answer")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("aidx", type=int)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_update_answer)

    p = subparsers.add_parser("delete-answer")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("aidx", type=int)
    p.set_defaults(func=cmd_delete_answer)

    p = subparsers.add_parser("get-followups")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.set_defaults(func=cmd_get_followups)

    p = subparsers.add_parser("save-followups")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("--data", required=True)
    p.set_defaults(func=cmd_save_followups)

    p = subparsers.add_parser("add-section")
    p.add_argument("name")
    p.add_argument("--section", required=True)
    p.set_defaults(func=cmd_add_section)

    p = subparsers.add_parser("rename-section")
    p.add_argument("name")
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.set_defaults(func=cmd_rename_section)

    p = subparsers.add_parser("delete-section")
    p.add_argument("name")
    p.add_argument("--section", required=True)
    p.add_argument("--action", choices=["uncategorized", "delete", "move"], default="uncategorized")
    p.add_argument("--target")
    p.set_defaults(func=cmd_delete_section)

    p = subparsers.add_parser("get-model-db-path")
    p.add_argument("name")
    p.set_defaults(func=cmd_get_model_db_path)

    p = subparsers.add_parser("import-db")
    p.add_argument("name", nargs="?")  # optional name for the new model
    p.add_argument("--file", required=True)
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd_import_db)

    args = parser.parse_args()
    kwargs = {k: v for k, v in vars(args).items() if k not in ('func', 'command') and v is not None}
    result = args.func(**kwargs)
    print(json.dumps(result))

if __name__ == "__main__":
    main()