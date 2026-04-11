import sqlite3
from typing import List, Dict, Optional
from .helpers import _get_fallback_id, _get_fallback_name
from ..utils.msgpack_helpers import pack_array, unpack_array
from .blob_utils import store_blob, release_blob, get_blob_data

def _store_node_qa(conn: sqlite3.Connection, questions: List[str], answers: List[str]) -> tuple:
    q_raw = pack_array(questions)
    a_raw = pack_array(answers)
    q_id = store_blob(conn, q_raw, normalise=True)
    a_id = store_blob(conn, a_raw, normalise=False)
    return q_id, a_id

def insert_followup_tree(conn: sqlite3.Connection, group_id: int, tree: List[Dict], parent_id: Optional[int] = None):
    for node in tree:
        questions = node.get("questions", [])
        answers = node.get("answers", [])
        q_id, a_id = _store_node_qa(conn, questions, answers)
        fallback_id = node.get("fallback_id")
        if fallback_id is None and "fallback" in node:
            fallback_id = _get_fallback_id(conn, node["fallback"])
        cursor = conn.execute(
            """INSERT INTO followup_nodes
               (group_id, parent_id, branch_name, questions_blob_id, answers_blob_id, fallback_id)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (group_id, parent_id, node.get("branch_name", ""), q_id, a_id, fallback_id)
        )
        node_id = cursor.fetchone()[0]
        if node.get("children"):
            insert_followup_tree(conn, group_id, node["children"], parent_id=node_id)

def delete_followup_tree(conn: sqlite3.Connection, group_id: int):
    cur = conn.execute("SELECT id, questions_blob_id, answers_blob_id FROM followup_nodes WHERE group_id = ?", (group_id,))
    nodes = cur.fetchall()
    for nid, q_id, a_id in nodes:
        release_blob(conn, q_id)
        release_blob(conn, a_id)
    conn.execute("DELETE FROM followup_nodes WHERE group_id = ?", (group_id,))

def load_followup_tree_skeleton(conn: sqlite3.Connection, group_id: int, parent_id: Optional[int] = None) -> List[Dict]:
    if parent_id is None:
        cur = conn.execute(
            "SELECT id, branch_name, fallback_id FROM followup_nodes WHERE group_id = ? AND parent_id IS NULL ORDER BY id",
            (group_id,)
        )
    else:
        cur = conn.execute(
            "SELECT id, branch_name, fallback_id FROM followup_nodes WHERE parent_id = ? ORDER BY id",
            (parent_id,)
        )
    nodes = []
    for row in cur:
        node = {
            "id": row[0],
            "branch_name": row[1],
            "fallback": _get_fallback_name(conn, row[2])
        }
        node["children"] = load_followup_tree_skeleton(conn, group_id, parent_id=row[0])
        nodes.append(node)
    return nodes

def load_followup_tree_full(conn: sqlite3.Connection, group_id: int, parent_id: Optional[int] = None) -> List[Dict]:
    if parent_id is None:
        cur = conn.execute(
            "SELECT id, branch_name, questions_blob_id, answers_blob_id, fallback_id FROM followup_nodes WHERE group_id = ? AND parent_id IS NULL ORDER BY id",
            (group_id,)
        )
    else:
        cur = conn.execute(
            "SELECT id, branch_name, questions_blob_id, answers_blob_id, fallback_id FROM followup_nodes WHERE parent_id = ? ORDER BY id",
            (parent_id,)
        )
    nodes = []
    for row in cur:
        q_raw = get_blob_data(conn, row[2])
        a_raw = get_blob_data(conn, row[3])
        questions = unpack_array(q_raw) if q_raw else []
        answers = unpack_array(a_raw) if a_raw else []
        node = {
            "id": row[0],
            "branch_name": row[1],
            "questions": questions,
            "answers": answers,
            "fallback": _get_fallback_name(conn, row[4])
        }
        node["children"] = load_followup_tree_full(conn, group_id, parent_id=row[0])
        nodes.append(node)
    return nodes

def merge_followup_trees(current_tree: List[Dict], incoming_tree: List[Dict]) -> List[Dict]:
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
                cnode = current_map[node_id]
                questions = inode.get('questions')
                if not questions:
                    questions = cnode.get('questions', [])
                answers = inode.get('answers')
                if not answers:
                    answers = cnode.get('answers', [])
                fallback = inode.get('fallback')
                if not fallback:
                    fallback = cnode.get('fallback', '')
                children = merge_nodes(inode.get('children', [])) if inode.get('children') else []
                merged.append({
                    'id': node_id,
                    'branch_name': inode.get('branch_name', cnode.get('branch_name', '')),
                    'questions': questions,
                    'answers': answers,
                    'fallback': fallback,
                    'children': children
                })
            else:
                children = merge_nodes(inode.get('children', [])) if inode.get('children') else []
                merged.append({
                    'branch_name': inode.get('branch_name', ''),
                    'questions': inode.get('questions', []),
                    'answers': inode.get('answers', []),
                    'fallback': inode.get('fallback', ''),
                    'children': children
                })
        return merged
    return merge_nodes(incoming_tree)