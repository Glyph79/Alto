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
    safe = safe_filename(model_name)
    return os.path.join(MODELS_BASE_DIR, folder, f"{safe}.db")

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
# Follow‑up node helpers (normalized) – lazy loading mandatory
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

def load_followup_tree_skeleton(conn: sqlite3.Connection, group_id: int, parent_id: Optional[int] = None) -> List[Dict]:
    """Recursively load only the structure (ids and branch names) of follow‑up nodes."""
    if parent_id is None:
        cur = conn.execute(
            "SELECT id, branch_name FROM followup_nodes WHERE group_id = ? AND parent_id IS NULL ORDER BY id",
            (group_id,)
        )
    else:
        cur = conn.execute(
            "SELECT id, branch_name FROM followup_nodes WHERE parent_id = ? ORDER BY id",
            (parent_id,)
        )
    nodes = []
    for row in cur:
        node = {
            "id": row[0],
            "branch_name": row[1],
        }
        node["children"] = load_followup_tree_skeleton(conn, group_id, parent_id=row[0])
        nodes.append(node)
    return nodes

def load_followup_tree_full(conn: sqlite3.Connection, group_id: int, parent_id: Optional[int] = None) -> List[Dict]:
    """Recursively load full follow‑up nodes with questions and answers."""
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
        }
        node["children"] = load_followup_tree_full(conn, group_id, parent_id=row[0])
        nodes.append(node)
    return nodes

def merge_followup_trees(current_tree: List[Dict], incoming_tree: List[Dict]) -> List[Dict]:
    """
    Merge incoming tree (with possibly missing Q&A) into current full tree.
    - Nodes in incoming that have an 'id' field: if their questions/answers are empty,
      replace with values from current tree (if node exists). Otherwise keep incoming.
    - Nodes in incoming without 'id' are new and kept as is.
    - Nodes in current not present in incoming are considered deleted and omitted.
    """
    # Build map of current nodes by id for quick lookup
    current_map = {}
    def build_map(nodes):
        for node in nodes:
            node_id = node.get('id')
            if node_id:
                current_map[node_id] = node
            if node.get('children'):
                build_map(node['children'])
    build_map(current_tree)

    def merge_nodes(incoming_nodes):
        merged = []
        for inode in incoming_nodes:
            node_id = inode.get('id')
            if node_id and node_id in current_map:
                # Existing node: copy Q&A from current if missing in incoming
                cnode = current_map[node_id]
                questions = inode.get('questions')
                if not questions:  # empty or None
                    questions = cnode.get('questions', [])
                answers = inode.get('answers')
                if not answers:
                    answers = cnode.get('answers', [])
                # Recursively merge children
                children = merge_nodes(inode.get('children', [])) if inode.get('children') else []
                merged.append({
                    'id': node_id,
                    'branch_name': inode.get('branch_name', cnode.get('branch_name', '')),
                    'questions': questions,
                    'answers': answers,
                    'children': children
                })
            else:
                # New node (no id) – keep as is, but ensure children merged recursively (though they should be new too)
                children = merge_nodes(inode.get('children', [])) if inode.get('children') else []
                merged.append({
                    'branch_name': inode.get('branch_name', ''),
                    'questions': inode.get('questions', []),
                    'answers': inode.get('answers', []),
                    'children': children
                })
        return merged

    return merge_nodes(incoming_tree)

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