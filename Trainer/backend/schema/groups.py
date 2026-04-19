import sqlite3
import datetime
from typing import List, Dict, Optional, Any, Tuple
from .helpers import _get_or_create_question_id, _get_topic_id, _get_fallback_id
from .followups import insert_followup_tree, delete_followup_tree
from ..utils.msgpack_helpers import pack_array, unpack_array
from .blob_utils import store_blob, release_blob, get_blob_data

def _store_qa_lists(conn: sqlite3.Connection, questions: List[str], answers: List[str]) -> tuple:
    q_raw = pack_array(questions)
    a_raw = pack_array(answers)
    q_id = store_blob(conn, q_raw, normalise=True)
    a_id = store_blob(conn, a_raw, normalise=False)
    return q_id, a_id

def insert_group(conn: sqlite3.Connection, model_name: str, group_dict: Dict[str, Any]) -> int:
    group_dict.setdefault("group_name", "New Group")
    questions = group_dict.get("questions", [])
    answers = group_dict.get("answers", [])
    
    # Check for topic_id first, then topic name
    topic_id = group_dict.get("topic_id")
    if topic_id is None:
        topic_name = group_dict.get("topic", "")
        topic_id = _get_topic_id(conn, topic_name)
    else:
        if topic_id == "" or topic_id is None:
            topic_id = None
        else:
            topic_id = int(topic_id) if isinstance(topic_id, str) else topic_id
    
    fallback_id = group_dict.get("fallback_id")
    if fallback_id is None and "fallback" in group_dict:
        fallback_id = _get_fallback_id(conn, group_dict["fallback"])

    q_id, a_id = _store_qa_lists(conn, questions, answers)
    a_count = len(answers)

    try:
        cursor = conn.execute(
            """INSERT INTO groups
               (group_name, topic_id, fallback_id, questions_blob_id, answers_blob_id, answer_count)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (group_dict["group_name"], topic_id, fallback_id, q_id, a_id, a_count)
        )
        group_id = cursor.fetchone()[0]

        for idx, q in enumerate(questions):
            qid = _get_or_create_question_id(conn, q)
            conn.execute(
                "INSERT INTO group_questions (group_id, question_id, sort_order) VALUES (?, ?, ?)",
                (group_id, qid, idx)
            )

        if "follow_ups" in group_dict and group_dict["follow_ups"]:
            insert_followup_tree(conn, group_id, group_dict["follow_ups"])
        conn.commit()
        return group_id
    except Exception:
        conn.rollback()
        raise

def update_group(conn: sqlite3.Connection, group_id: int, group_dict: Dict[str, Any]):
    group_dict.setdefault("group_name", "New Group")
    questions = group_dict.get("questions", [])
    answers = group_dict.get("answers", [])
    
    # Check for topic_id first, then topic name
    topic_id = group_dict.get("topic_id")
    if topic_id is None:
        topic_name = group_dict.get("topic", "")
        topic_id = _get_topic_id(conn, topic_name)
    else:
        if topic_id == "" or topic_id is None:
            topic_id = None
        else:
            topic_id = int(topic_id) if isinstance(topic_id, str) else topic_id
    
    fallback_id = group_dict.get("fallback_id")
    if fallback_id is None and "fallback" in group_dict:
        fallback_id = _get_fallback_id(conn, group_dict["fallback"])

    a_count = len(answers)

    cur = conn.execute("SELECT questions_blob_id, answers_blob_id FROM groups WHERE id = ?", (group_id,))
    old_q_id, old_a_id = cur.fetchone()

    q_id, a_id = _store_qa_lists(conn, questions, answers)

    try:
        conn.execute(
            """UPDATE groups SET group_name = ?, topic_id = ?, fallback_id = ?,
               questions_blob_id = ?, answers_blob_id = ?, answer_count = ?
               WHERE id = ?""",
            (group_dict["group_name"], topic_id, fallback_id, q_id, a_id, a_count, group_id)
        )
        release_blob(conn, old_q_id)
        release_blob(conn, old_a_id)

        conn.execute("DELETE FROM group_questions WHERE group_id = ?", (group_id,))
        for idx, q in enumerate(questions):
            qid = _get_or_create_question_id(conn, q)
            conn.execute(
                "INSERT INTO group_questions (group_id, question_id, sort_order) VALUES (?, ?, ?)",
                (group_id, qid, idx)
            )

        if "follow_ups" in group_dict:
            delete_followup_tree(conn, group_id)
            if group_dict["follow_ups"]:
                insert_followup_tree(conn, group_id, group_dict["follow_ups"])

        conn.commit()
    except Exception:
        conn.rollback()
        raise

def delete_group(conn: sqlite3.Connection, group_id: int):
    cur = conn.execute("SELECT questions_blob_id, answers_blob_id FROM groups WHERE id = ?", (group_id,))
    row = cur.fetchone()
    if row:
        q_id, a_id = row
        release_blob(conn, q_id)
        release_blob(conn, a_id)
    conn.execute("DELETE FROM followup_nodes WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))

def get_group_by_id(conn: sqlite3.Connection, group_id: int, include_followups: bool = False) -> Dict:
    from .helpers import _get_topic_name, _get_fallback_name
    from .followups import load_followup_tree_full
    cur = conn.execute("""
        SELECT g.id, g.group_name, g.topic_id, g.fallback_id,
               g.questions_blob_id, g.answers_blob_id
        FROM groups g
        WHERE g.id = ?
    """, (group_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Group id {group_id} not found")
    questions_raw = get_blob_data(conn, row[4])
    answers_raw = get_blob_data(conn, row[5])
    questions = unpack_array(questions_raw) if questions_raw else []
    answers = unpack_array(answers_raw) if answers_raw else []
    group = {
        "id": row[0],
        "group_name": row[1],
        "topic_id": row[2],
        "topic": _get_topic_name(conn, row[2]),
        "fallback": _get_fallback_name(conn, row[3]),
        "questions": questions,
        "answers": answers
    }
    if include_followups:
        group["follow_ups"] = load_followup_tree_full(conn, group_id)
    return group

def get_group_summaries(conn: sqlite3.Connection) -> List[Dict]:
    cur = conn.execute("""
        SELECT g.id, g.group_name,
               COALESCE(t.name, '') as topic,
               (SELECT GROUP_CONCAT(q.text, '|') FROM group_questions gq JOIN questions q ON gq.question_id = q.id WHERE gq.group_id = g.id ORDER BY gq.sort_order) as questions_text
        FROM groups g
        LEFT JOIN topics t ON g.topic_id = t.id
        ORDER BY g.id
    """)
    summaries = []
    for row in cur:
        summaries.append({
            "id": row[0],
            "group_name": row[1],
            "topic": row[2],
            "questions": row[3].split('|') if row[3] else []
        })
    return summaries

def get_group_summaries_with_counts(conn: sqlite3.Connection, limit: int, offset: int) -> Tuple[List[Dict], int]:
    cur = conn.execute("SELECT COUNT(*) FROM groups")
    total = cur.fetchone()[0]

    cur = conn.execute("""
        SELECT g.id, g.group_name,
               COALESCE(t.name, '') as topic,
               (SELECT COUNT(*) FROM group_questions WHERE group_id = g.id) as question_count,
               g.answer_count
        FROM groups g
        LEFT JOIN topics t ON g.topic_id = t.id
        ORDER BY g.id
        LIMIT ? OFFSET ?
    """, (limit, offset))
    summaries = []
    for row in cur:
        summaries.append({
            "id": row[0],
            "group_name": row[1],
            "topic": row[2],
            "question_count": row[3],
            "answer_count": row[4]
        })
    return summaries, total