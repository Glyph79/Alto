import os
import re
import datetime
import sqlite3
import msgpack
import shutil
import time
from typing import List, Dict, Optional, Any

MODELS_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
os.makedirs(MODELS_BASE_DIR, exist_ok=True)

# ----------------------------------------------------------------------
# Filename helpers
# ----------------------------------------------------------------------
def safe_filename(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)

def timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")

def find_model_dir(model_name: str) -> Optional[str]:
    safe = safe_filename(model_name)
    if not os.path.exists(MODELS_BASE_DIR):
        return None
    for entry in os.listdir(MODELS_BASE_DIR):
        full_path = os.path.join(MODELS_BASE_DIR, entry)
        if not os.path.isdir(full_path):
            continue
        if entry.endswith('_' + safe):
            return entry
    return None

def ensure_model_dir(model_name: str) -> str:
    safe = safe_filename(model_name)
    base = f"{timestamp()}_{safe}"
    candidate = base
    counter = 1
    while os.path.exists(os.path.join(MODELS_BASE_DIR, candidate)):
        candidate = f"{base}_{counter}"
        counter += 1
    full_path = os.path.join(MODELS_BASE_DIR, candidate)
    os.makedirs(full_path, exist_ok=True)
    return candidate

def get_model_db_path(model_name: str) -> Optional[str]:
    folder = find_model_dir(model_name)
    if not folder:
        return None
    return os.path.join(MODELS_BASE_DIR, folder, "model.db")

# ----------------------------------------------------------------------
# MsgPack helpers
# ----------------------------------------------------------------------
def pack_array(arr: List) -> bytes:
    return msgpack.packb(arr, use_bin_type=True)

def unpack_array(data: bytes) -> List:
    return msgpack.unpackb(data, raw=False)

# ----------------------------------------------------------------------
# FTS index helper
# ----------------------------------------------------------------------
def update_fts_index(conn: sqlite3.Connection, group_id: int, questions: List[str]):
    conn.execute("DELETE FROM questions_fts WHERE group_id = ?", (group_id,))
    for question in questions:
        conn.execute("INSERT INTO questions_fts(group_id, question) VALUES (?, ?)", (group_id, question))

# ----------------------------------------------------------------------
# Follow‑up node helpers (normalized)
# ----------------------------------------------------------------------
def insert_followup_tree(conn: sqlite3.Connection, group_id: int, tree: List[Dict], parent_id: Optional[int] = None):
    for node in tree:
        questions_blob = pack_array(node.get("questions", []))
        answers_blob = pack_array(node.get("answers", []))
        cursor = conn.execute(
            """INSERT INTO followup_nodes (group_id, parent_id, branch_name, questions_blob, answers_blob)
               VALUES (?, ?, ?, ?, ?) RETURNING id""",
            (group_id, parent_id, node.get("branch_name", ""), questions_blob, answers_blob)
        )
        node_id = cursor.fetchone()[0]
        if node.get("children"):
            insert_followup_tree(conn, group_id, node["children"], parent_id=node_id)

def delete_followup_tree(conn: sqlite3.Connection, group_id: int):
    conn.execute("DELETE FROM followup_nodes WHERE group_id = ?", (group_id,))

def load_followup_tree(conn: sqlite3.Connection, group_id: int, parent_id: Optional[int] = None) -> List[Dict]:
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
            "questions": unpack_array(row[2]),
            "answers": unpack_array(row[3]),
            "children": load_followup_tree(conn, group_id, parent_id=row[0])
        }
        nodes.append(node)
    return nodes

# ----------------------------------------------------------------------
# Import/Export helper
# ----------------------------------------------------------------------
def delete_with_retry(path, max_attempts=5, delay=0.1):
    for attempt in range(max_attempts):
        try:
            shutil.rmtree(path)
            return True
        except Exception:
            if attempt == max_attempts - 1:
                raise
            time.sleep(delay * (2 ** attempt))
    return False