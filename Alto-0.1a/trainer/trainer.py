#!/usr/bin/env python3
"""
Alto Trainer – per‑model SQLite backend with MessagePack BLOBs and FTS5 full‑text search.
Normalized follow‑up nodes for memory‑efficient AI.
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
import time
from typing import Any, Dict, List, Optional

MODELS_BASE_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_BASE_DIR, exist_ok=True)

# ----------------------------------------------------------------------
# Filename helpers
# ----------------------------------------------------------------------
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

# ----------------------------------------------------------------------
# MsgPack helpers
# ----------------------------------------------------------------------
def _pack_array(arr: List) -> bytes:
    return msgpack.packb(arr, use_bin_type=True)

def _unpack_array(data: bytes) -> List:
    return msgpack.unpackb(data, raw=False)

# ----------------------------------------------------------------------
# FTS index helper
# ----------------------------------------------------------------------
def _update_fts_index(conn: sqlite3.Connection, group_id: int, questions: List[str]):
    conn.execute("DELETE FROM questions_fts WHERE group_id = ?", (group_id,))
    for question in questions:
        conn.execute("INSERT INTO questions_fts(group_id, question) VALUES (?, ?)", (group_id, question))

# ----------------------------------------------------------------------
# Follow‑up node helpers (normalized)
# ----------------------------------------------------------------------
def _insert_followup_tree(conn: sqlite3.Connection, group_id: int, tree: List[Dict], parent_id: Optional[int] = None):
    """Recursively insert follow‑up nodes into followup_nodes table."""
    for node in tree:
        questions_blob = _pack_array(node.get("questions", []))
        answers_blob = _pack_array(node.get("answers", []))
        cursor = conn.execute(
            """INSERT INTO followup_nodes (group_id, parent_id, branch_name, questions_blob, answers_blob)
               VALUES (?, ?, ?, ?, ?) RETURNING id""",
            (group_id, parent_id, node.get("branch_name", ""), questions_blob, answers_blob)
        )
        node_id = cursor.fetchone()[0]
        if node.get("children"):
            _insert_followup_tree(conn, group_id, node["children"], parent_id=node_id)

def _delete_followup_tree(conn: sqlite3.Connection, group_id: int):
    """Delete all follow‑up nodes for a group."""
    conn.execute("DELETE FROM followup_nodes WHERE group_id = ?", (group_id,))

def _load_followup_tree(conn: sqlite3.Connection, group_id: int, parent_id: Optional[int] = None) -> List[Dict]:
    """Recursively load follow‑up nodes from followup_nodes table."""
    if parent_id is None:
        cur = conn.execute(
            "SELECT id, branch_name, questions_blob, answers_blob FROM followup_nodes WHERE group_id = ? AND parent_id IS NULL ORDER BY id",
            (group_id,)
        )
    else:
        cur = conn.execute(
            "SELECT id, branch_name, questions_blob, answers_blob FROM followup_nodes WHERE parent_id = ? ORDER BY id",
            (parent_id,)
        )
    nodes = []
    for row in cur:
        node = {
            "id": row[0],
            "branch_name": row[1],
            "questions": _unpack_array(row[2]),
            "answers": _unpack_array(row[3]),
            "children": _load_followup_tree(conn, group_id, parent_id=row[0])
        }
        nodes.append(node)
    return nodes

# ----------------------------------------------------------------------
# Model DB initialization (new schema)
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
            answers_blob BLOB NOT NULL
        )
    """)
    # FTS5 virtual table for questions
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts USING fts5(
            group_id UNINDEXED,
            question
        )
    """)
    # Normalized follow‑up nodes table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS followup_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            parent_id INTEGER,
            branch_name TEXT NOT NULL,
            questions_blob BLOB NOT NULL,
            answers_blob BLOB NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_id) REFERENCES followup_nodes(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_followup_nodes_group ON followup_nodes(group_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_followup_nodes_parent ON followup_nodes(parent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_section ON groups(section)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_topic ON groups(topic)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_priority ON groups(priority)")

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
# Group operations (no persistent group cache)
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
        # follow_ups are loaded separately
    }

def _insert_group(conn: sqlite3.Connection, model_name: str, group_dict: Dict[str, Any]) -> int:
    group_dict.setdefault("group_name", "New Group")
    group_dict.setdefault("questions", [])
    group_dict.setdefault("answers", [])
    group_dict.setdefault("topic", "general")
    group_dict.setdefault("priority", "medium")
    group_dict.setdefault("section", "")

    questions_blob = _pack_array(group_dict["questions"])
    answers_blob = _pack_array(group_dict["answers"])

    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """INSERT INTO groups (group_name, topic, priority, section, questions_blob, answers_blob)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (group_dict["group_name"], group_dict["topic"], group_dict["priority"],
             group_dict["section"], questions_blob, answers_blob)
        )
        group_id = cursor.fetchone()[0]
        _update_fts_index(conn, group_id, group_dict["questions"])
        # Insert follow‑ups if provided
        if "follow_ups" in group_dict and group_dict["follow_ups"]:
            _insert_followup_tree(conn, group_id, group_dict["follow_ups"])
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

    questions_blob = _pack_array(group_dict["questions"])
    answers_blob = _pack_array(group_dict["answers"])

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """UPDATE groups SET group_name = ?, topic = ?, priority = ?, section = ?,
               questions_blob = ?, answers_blob = ? WHERE id = ?""",
            (group_dict["group_name"], group_dict["topic"], group_dict["priority"],
             group_dict["section"], questions_blob, answers_blob, group_id)
        )
        _update_fts_index(conn, group_id, group_dict["questions"])
        # Replace follow‑ups
        _delete_followup_tree(conn, group_id)
        if "follow_ups" in group_dict and group_dict["follow_ups"]:
            _insert_followup_tree(conn, group_id, group_dict["follow_ups"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def _delete_group(conn: sqlite3.Connection, group_id: int):
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM questions_fts WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM followup_nodes WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

# ----------------------------------------------------------------------
# Model class (caches summaries only)
# ----------------------------------------------------------------------
class Model:
    def __init__(self, name: str):
        self.name = name
        db_path = _get_model_db_path(name)
        if not db_path:
            raise FileNotFoundError(f"Model '{name}' not found")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA cache_size = -20000")
        self.conn.execute("PRAGMA mmap_size = 30000000000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row

        self._group_summaries = None

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _load_group_summaries(self):
        cur = self.conn.execute(
            "SELECT id, group_name, topic, priority, section FROM groups ORDER BY id"
        )
        self._group_summaries = [dict(row) for row in cur]

    def get_group_summaries(self) -> List[Dict]:
        if self._group_summaries is None:
            self._load_group_summaries()
        return self._group_summaries

    def get_group_by_index(self, index: int) -> Dict:
        summaries = self.get_group_summaries()
        if index < 0 or index >= len(summaries):
            raise IndexError("Group index out of range")
        group_id = summaries[index]["id"]
        return self.get_group_by_id(group_id)

    def get_group_by_id(self, group_id: int) -> Dict:
        cur = self.conn.execute(
            "SELECT id, group_name, topic, priority, section, "
            "questions_blob, answers_blob FROM groups WHERE id = ?",
            (group_id,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Group id {group_id} not found")
        group = _group_from_row(row)
        # Load follow‑ups
        group["follow_ups"] = _load_followup_tree(self.conn, group_id)
        return group

    def get_all_groups_full(self) -> List[Dict]:
        summaries = self.get_group_summaries()
        full_groups = []
        for s in summaries:
            g = self.get_group_by_id(s["id"])
            full_groups.append(g)
        return full_groups

    def insert_group(self, group_dict: Dict) -> int:
        group_id = _insert_group(self.conn, self.name, group_dict)
        self._group_summaries = None
        return group_id

    def update_group(self, group_id: int, group_dict: Dict):
        _update_group(self.conn, group_id, group_dict)
        self._group_summaries = None

    def delete_group(self, group_id: int):
        _delete_group(self.conn, group_id)
        self._group_summaries = None

# Global model cache
_model_cache: Dict[str, Model] = {}

def _get_model(name: str) -> Model:
    if name not in _model_cache:
        _model_cache[name] = Model(name)
    return _model_cache[name]

def _close_all_models():
    for model in _model_cache.values():
        model.close()
    _model_cache.clear()

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
        model = _get_model(name)
        info = _get_model_info(model.conn)
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
        model = _get_model(name)
        updates = {}
        if description is not None:
            updates["description"] = description
        if author is not None:
            updates["author"] = author
        if version is not None:
            updates["version"] = version
        new_info = _update_model_info(model.conn, **updates)
        return {"status": "ok", "model": new_info}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_model(name: str, **kwargs) -> Dict:
    if name in _model_cache:
        _model_cache[name].close()
        del _model_cache[name]

    folder = _find_model_dir(name)
    if not folder:
        return {"error": f"Model '{name}' not found"}

    model_path = os.path.join(MODELS_BASE_DIR, folder)
    try:
        shutil.rmtree(model_path)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_rename_model(name: str, new_name: str, **kwargs) -> Dict:
    # Check if old model exists
    old_folder = _find_model_dir(name)
    if not old_folder:
        return {"error": f"Model '{name}' not found"}

    # Check if new name already exists
    if _find_model_dir(new_name) is not None:
        return {"error": f"Model '{new_name}' already exists"}

    # Close model if open in cache
    if name in _model_cache:
        _model_cache[name].close()
        del _model_cache[name]

    old_path = os.path.join(MODELS_BASE_DIR, old_folder)
    # Build new folder name: keep same timestamp, use safe new name
    timestamp = old_folder.split('_')[0]  # assumes format YYYY-MM-DD_safe_name
    safe_new = _safe_filename(new_name)
    new_folder = f"{timestamp}_{safe_new}"
    new_path = os.path.join(MODELS_BASE_DIR, new_folder)

    # Ensure uniqueness (should not happen because we checked _find_model_dir)
    counter = 1
    while os.path.exists(new_path):
        new_folder = f"{timestamp}_{safe_new}_{counter}"
        new_path = os.path.join(MODELS_BASE_DIR, new_folder)
        counter += 1

    try:
        # Rename folder
        os.rename(old_path, new_path)
        # Update database inside the moved folder
        db_path = os.path.join(new_path, "model.db")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE model_info SET name = ? WHERE name = ?", (new_name, name))
        conn.commit()
        conn.close()
        return {"status": "ok", "old_name": name, "new_name": new_name}
    except Exception as e:
        # Attempt to rollback rename if something fails
        if os.path.exists(new_path) and not os.path.exists(old_path):
            os.rename(new_path, old_path)
        return {"error": f"Rename failed: {str(e)}"}

def cmd_add_group(name: str, data: str, **kwargs) -> Dict:
    try:
        group_dict = json.loads(data)
        model = _get_model(name)
        group_id = model.insert_group(group_dict)
        return {"status": "ok", "group_id": group_id}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_group(name: str, index: int, data: str, **kwargs) -> Dict:
    try:
        group_dict = json.loads(data)
        model = _get_model(name)
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
        model = _get_model(name)
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
        model = _get_model(name)
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
        model = _get_model(name)
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
        model = _get_model(name)
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
        model = _get_model(name)
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
        model = _get_model(name)
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
        model = _get_model(name)
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
        model = _get_model(name)
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
        model = _get_model(name)
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
        model = _get_model(name)
        info = _get_model_info(model.conn)
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
        model = _get_model(name)
        conn = model.conn
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
        model = _get_model(name)
        conn = model.conn
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
        model._group_summaries = None
        return {"status": "ok"}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}

# ----------------------------------------------------------------------
# Import/Export helpers
# ----------------------------------------------------------------------
def delete_with_retry(path, max_attempts=5, delay=0.1):
    for attempt in range(max_attempts):
        try:
            shutil.rmtree(path)
            return True
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            time.sleep(delay * (2 ** attempt))
    return False

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

    existing_dir = _find_model_dir(final_name)
    if existing_dir is not None:
        print(f"[DEBUG] Model '{final_name}' already exists at {existing_dir}", file=sys.stderr)
        if overwrite:
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

    folder = _ensure_model_dir(final_name)
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
        info = _get_model_info(conn)
        conn.close()
        print(f"[DEBUG] Import successful for '{final_name}'", file=sys.stderr)
        return {"status": "ok", "model": info}
    except Exception as e:
        shutil.rmtree(os.path.join(MODELS_BASE_DIR, folder), ignore_errors=True)
        print(f"[DEBUG] Import failed: {str(e)}", file=sys.stderr)
        return {"error": f"Failed to import database: {str(e)}"}

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
                result = COMMANDS[cmd](**kwargs)
        except FileNotFoundError as e:
            result = {"error": str(e)}
        except Exception as e:
            result = {"error": str(e)}
        print(json.dumps(result), flush=True)
    _close_all_models()

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

    p = subparsers.add_parser("rename-model")
    p.add_argument("name")
    p.add_argument("new_name")
    p.set_defaults(func=cmd_rename_model)

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
    p.add_argument("name", nargs="?")
    p.add_argument("--file", required=True)
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd_import_db)

    args = parser.parse_args()
    kwargs = {k: v for k, v in vars(args).items() if k not in ('func', 'command') and v is not None}
    result = args.func(**kwargs)
    print(json.dumps(result))

if __name__ == "__main__":
    main()