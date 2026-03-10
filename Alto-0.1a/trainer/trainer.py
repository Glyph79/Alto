#!/usr/bin/env python3
"""
Alto Trainer – per‑model SQLite backend with MessagePack BLOBs and word index.
Each model is stored in models/<model_name>/<model_name>.db.
The CLI interface is identical to the original LMDB version.
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
from typing import Any, Dict, List, Optional

# ----------------------------------------------------------------------
# Base directory for all models
# ----------------------------------------------------------------------
MODELS_BASE_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_BASE_DIR, exist_ok=True)

_connection_cache: Dict[str, sqlite3.Connection] = {}

def _safe_filename(name: str) -> str:
    """Make a string safe for use as a folder/file name."""
    return name.replace('/', '_').replace('\\', '_').replace(':', '_')

def _get_model_dir(model_name: str) -> str:
    safe = _safe_filename(model_name)
    return os.path.join(MODELS_BASE_DIR, safe)

def _get_model_db_path(model_name: str) -> str:
    return os.path.join(_get_model_dir(model_name), f"{model_name}.db")

def _ensure_model_dir(model_name: str):
    os.makedirs(_get_model_dir(model_name), exist_ok=True)

def _connect_model_db(model_name: str, use_cache: bool = False) -> sqlite3.Connection:
    if use_cache and model_name in _connection_cache:
        return _connection_cache[model_name]

    db_path = _get_model_db_path(model_name)
    conn = sqlite3.connect(db_path, check_same_thread=False)

    # Performance optimisations
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -20000")
    conn.execute("PRAGMA mmap_size = 30000000000")
    conn.execute("PRAGMA foreign_keys = ON")

    if use_cache:
        _connection_cache[model_name] = conn
    return conn

def _close_all_connections():
    for conn in _connection_cache.values():
        conn.close()
    _connection_cache.clear()

def _normalize_word(word: str) -> str:
    """Lowercase and strip punctuation for indexing."""
    return re.sub(r'[^\w\s]', '', word.lower())

def _update_word_index(conn: sqlite3.Connection, group_id: int, questions: List[str]):
    """
    Replace the word index for a group with fresh entries from its questions.
    Uses a dictionary table `words` to store each unique word only once.
    """
    # Delete old entries for this group
    conn.execute("DELETE FROM word_index WHERE group_id = ?", (group_id,))

    # Insert new entries for each word in each question
    for q_idx, question in enumerate(questions):
        words = question.split()
        for word in words:
            norm = _normalize_word(word)
            if not norm:
                continue
            # Ensure the word exists in the words table
            cur = conn.execute(
                "INSERT OR IGNORE INTO words (word) VALUES (?)",
                (norm,)
            )
            # Get its ID (whether newly inserted or existing)
            cur = conn.execute("SELECT id FROM words WHERE word = ?", (norm,))
            word_id = cur.fetchone()[0]
            conn.execute(
                "INSERT INTO word_index (word_id, group_id, question_idx) VALUES (?, ?, ?)",
                (word_id, group_id, q_idx)
            )

def _init_model_db(conn: sqlite3.Connection, model_name: str, description: str, author: str, version: str):
    """Create tables and indexes."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_info (
            name TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            author TEXT NOT NULL,
            version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sections TEXT NOT NULL   -- JSON array
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            topic TEXT NOT NULL,
            priority TEXT NOT NULL,
            section TEXT NOT NULL,
            data BLOB NOT NULL
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

def _pack_group(group_dict: Dict[str, Any]) -> bytes:
    return msgpack.packb(group_dict, use_bin_type=True)

def _unpack_group(data: bytes) -> Dict[str, Any]:
    return msgpack.unpackb(data, raw=False)

def _group_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    group_id, group_name, topic, priority, section, blob = row
    group = _unpack_group(blob)
    group["id"] = group_id
    group["group_name"] = group_name
    group["topic"] = topic
    group["priority"] = priority
    group["section"] = section
    return group

def _insert_group(conn: sqlite3.Connection, model_name: str, group_dict: Dict[str, Any]) -> int:
    group_dict.setdefault("group_name", "New Group")
    group_dict.setdefault("questions", [])
    group_dict.setdefault("answers", [])
    group_dict.setdefault("topic", "general")
    group_dict.setdefault("priority", "medium")
    group_dict.setdefault("section", "")
    group_dict.setdefault("follow_ups", [])

    blob = _pack_group(group_dict)
    cursor = conn.execute(
        """INSERT INTO groups (group_name, topic, priority, section, data)
           VALUES (?, ?, ?, ?, ?) RETURNING id""",
        (group_dict["group_name"], group_dict["topic"], group_dict["priority"],
         group_dict["section"], blob)
    )
    group_id = cursor.fetchone()[0]

    # Update word index for questions
    _update_word_index(conn, group_id, group_dict["questions"])

    conn.commit()
    return group_id

def _update_group(conn: sqlite3.Connection, group_id: int, group_dict: Dict[str, Any]):
    group_dict.setdefault("group_name", "New Group")
    group_dict.setdefault("questions", [])
    group_dict.setdefault("answers", [])
    group_dict.setdefault("topic", "general")
    group_dict.setdefault("priority", "medium")
    group_dict.setdefault("section", "")
    group_dict.setdefault("follow_ups", [])

    blob = _pack_group(group_dict)
    conn.execute(
        """UPDATE groups SET group_name = ?, topic = ?, priority = ?, section = ?, data = ?
           WHERE id = ?""",
        (group_dict["group_name"], group_dict["topic"], group_dict["priority"],
         group_dict["section"], blob, group_id)
    )

    # Update word index
    _update_word_index(conn, group_id, group_dict["questions"])

    conn.commit()

def _delete_group(conn: sqlite3.Connection, group_id: int):
    # Foreign key cascade will remove word_index entries automatically
    conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    conn.commit()

def _get_all_groups(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    cur = conn.execute("SELECT id, group_name, topic, priority, section, data FROM groups ORDER BY id")
    groups = []
    for row in cur:
        groups.append(_group_from_row(row))
    return groups

def _get_group_by_index(conn: sqlite3.Connection, index: int) -> Dict[str, Any]:
    groups = _get_all_groups(conn)
    if index < 0 or index >= len(groups):
        raise IndexError("Group index out of range")
    return groups[index]

def _update_group_by_index(conn: sqlite3.Connection, index: int, new_data: Dict[str, Any]):
    groups = _get_all_groups(conn)
    if index < 0 or index >= len(groups):
        raise IndexError("Group index out of range")
    group_id = groups[index]["id"]
    _update_group(conn, group_id, new_data)

def _delete_group_by_index(conn: sqlite3.Connection, index: int):
    groups = _get_all_groups(conn)
    if index < 0 or index >= len(groups):
        raise IndexError("Group index out of range")
    group_id = groups[index]["id"]
    _delete_group(conn, group_id)

# ----------------------------------------------------------------------
# Command handlers (identical JSON interface)
# ----------------------------------------------------------------------
def cmd_list_models(**kwargs) -> List[str]:
    models = []
    if not os.path.exists(MODELS_BASE_DIR):
        return []
    for entry in os.listdir(MODELS_BASE_DIR):
        model_dir = os.path.join(MODELS_BASE_DIR, entry)
        if os.path.isdir(model_dir):
            db_path = os.path.join(model_dir, f"{entry}.db")
            if os.path.isfile(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cur = conn.execute("SELECT name FROM model_info")
                    row = cur.fetchone()
                    conn.close()
                    if row:
                        models.append(row[0])
                except:
                    pass
    return sorted(models)

def cmd_create_model(name: str, description: str = "", author: str = "", version: str = "1.0.0", **kwargs) -> Dict:
    model_dir = _get_model_dir(name)
    db_path = _get_model_db_path(name)
    if os.path.exists(db_path):
        return {"error": f"Model '{name}' already exists"}

    _ensure_model_dir(name)
    conn = _connect_model_db(name, use_cache=False)
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
            del g["id"]  # internal field not part of JSON
        return {**info, "qa_groups": groups}
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
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_delete_model(name: str, **kwargs) -> Dict:
    model_dir = _get_model_dir(name)
    if not os.path.isdir(model_dir):
        return {"error": f"Model '{name}' not found"}
    try:
        shutil.rmtree(model_dir)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_add_group(name: str, data: str, **kwargs) -> Dict:
    try:
        group_dict = json.loads(data)
        conn = _connect_model_db(name, use_cache=False)
        group_id = _insert_group(conn, name, group_dict)
        return {"status": "ok", "group_id": group_id}
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
    except IndexError:
        return {"error": "Group index out of range"}
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
    except IndexError:
        return {"error": "Group index out of range"}
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
    except IndexError:
        return {"error": "Group index out of range"}
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
    except IndexError:
        return {"error": "Group index out of range"}
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
    except IndexError:
        return {"error": "Group index out of range"}
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
    except IndexError:
        return {"error": "Group index out of range"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_get_followups(name: str, index: int, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        group = _get_group_by_index(conn, index)
        return group.get("follow_ups", [])
    except IndexError:
        return {"error": "Group index out of range"}
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
    except IndexError:
        return {"error": "Group index out of range"}
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
        cur = conn.execute("SELECT id, data FROM groups WHERE section = ?", (old,))
        rows = cur.fetchall()
        for row in rows:
            group_id, blob = row
            group = _unpack_group(blob)
            group["section"] = new
            new_blob = _pack_group(group)
            conn.execute(
                "UPDATE groups SET section = ?, data = ? WHERE id = ?",
                (new, new_blob, group_id)
            )
        conn.commit()
        return {"status": "ok"}
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
            cur = conn.execute("SELECT id, data FROM groups WHERE section = ?", (section,))
            rows = cur.fetchall()
            for row in rows:
                group_id, blob = row
                group = _unpack_group(blob)
                group["section"] = ""
                new_blob = _pack_group(group)
                conn.execute(
                    "UPDATE groups SET section = ?, data = ? WHERE id = ?",
                    ("", new_blob, group_id)
                )
        elif action == "move":
            if not target:
                conn.rollback()
                return {"error": "Target section required for move action"}
            if target not in info["sections"] and target != "":
                conn.rollback()
                return {"error": f"Target section '{target}' not found"}
            cur = conn.execute("SELECT id, data FROM groups WHERE section = ?", (section,))
            rows = cur.fetchall()
            for row in rows:
                group_id, blob = row
                group = _unpack_group(blob)
                group["section"] = target
                new_blob = _pack_group(group)
                conn.execute(
                    "UPDATE groups SET section = ?, data = ? WHERE id = ?",
                    (target, new_blob, group_id)
                )
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
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_import(name: str, file: str, **kwargs) -> Dict:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        conn = _connect_model_db(name, use_cache=False)
        try:
            info = _get_model_info(conn)
        except:
            return {"error": f"Model '{name}' not found or corrupt"}

        conn.execute("BEGIN IMMEDIATE")

        if isinstance(data, dict) and "sections" in data:
            info["sections"] = data["sections"]
            info["updated_at"] = datetime.datetime.now().isoformat()
            conn.execute(
                "UPDATE model_info SET sections = ?, updated_at = ? WHERE name = ?",
                (json.dumps(info["sections"], separators=(',', ':')), info["updated_at"], info["name"])
            )

        if isinstance(data, dict) and "qa_groups" in data:
            groups = data["qa_groups"]
        elif isinstance(data, list):
            groups = data
        else:
            groups = [data]

        count = 0
        for g in groups:
            _insert_group(conn, name, g)
            count += 1

        conn.commit()
        return {"status": "ok", "imported": count}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()

def cmd_export(name: str, **kwargs) -> Dict:
    try:
        conn = _connect_model_db(name, use_cache=False)
        info = _get_model_info(conn)
        groups = _get_all_groups(conn)
        for g in groups:
            del g["id"]
        return {**info, "qa_groups": groups}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

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
    "import":           cmd_import,
    "export":           cmd_export,
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
                if model_name and cmd not in ("list-models", "create-model"):
                    if model_name not in _connection_cache:
                        if not os.path.exists(_get_model_db_path(model_name)):
                            result = {"error": f"Model '{model_name}' not found"}
                            print(json.dumps(result), flush=True)
                            continue
                        _connection_cache[model_name] = _connect_model_db(model_name, use_cache=True)
                result = COMMANDS[cmd](**kwargs)
        except Exception as e:
            result = {"error": str(e)}
        print(json.dumps(result), flush=True)
    _close_all_connections()

def main():
    if "--interactive" in sys.argv:
        interactive_loop()
        return

    parser = argparse.ArgumentParser(description="Alto Trainer CLI (MsgPack BLOB + word index)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # (Subparsers identical to original – omitted for brevity, but must be included)
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

    p = subparsers.add_parser("import")
    p.add_argument("name")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_import)

    p = subparsers.add_parser("export")
    p.add_argument("name")
    p.set_defaults(func=cmd_export)

    args = parser.parse_args()
    kwargs = {k: v for k, v in vars(args).items() if k not in ('func', 'command') and v is not None}
    result = args.func(**kwargs)
    print(json.dumps(result))

if __name__ == "__main__":
    main()
