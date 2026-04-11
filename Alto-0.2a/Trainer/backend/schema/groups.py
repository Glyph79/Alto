import sqlite3
import datetime
from typing import List, Dict, Optional, Any
from .helpers import _get_or_create_question_id, _get_topic_id, _get_section_id, _get_fallback_id
from .followups import insert_followup_tree, delete_followup_tree
from ..utils.msgpack_helpers import pack_array, unpack_array
from .blob_utils import store_blob, release_blob, get_blob_data

def _store_qa_lists(conn: sqlite3.Connection, questions: List[str], answers: List[str]) -> tuple:
    q_raw = pack_array(questions)
    a_raw = pack_array(answers)
    q_id = store_blob(conn, q_raw, normalise=True)   # normalise questions
    a_id = store_blob(conn, a_raw, normalise=False)  # answers keep original
    return q_id, a_id

def insert_group(conn: sqlite3.Connection, model_name: str, group_dict: Dict[str, Any]) -> int:
    group_dict.setdefault("group_name", "New Group")
    questions = group_dict.get("questions", [])
    answers = group_dict.get("answers", [])
    topic_name = group_dict.get("topic", "")
    section_name = group_dict.get("section", "")
    fallback_id = group_dict.get("fallback_id")
    # Legacy support: if fallback_id is missing but "fallback" (name) is present, convert it
    if fallback_id is None and "fallback" in group_dict:
        fallback_id = _get_fallback_id(conn, group_dict["fallback"])

    topic_id = _get_topic_id(conn, topic_name)
    section_id = _get_section_id(conn, section_name)
    q_id, a_id = _store_qa_lists(conn, questions, answers)
    a_count = len(answers)
    now = datetime.datetime.now().isoformat()

    try:
        cursor = conn.execute(
            """INSERT INTO groups
               (group_name, topic_id, section_id, fallback_id, questions_blob_id, answers_blob_id, answer_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (group_dict["group_name"], topic_id, section_id, fallback_id, q_id, a_id, a_count, now, now)
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
    topic_name = group_dict.get("topic", "")
    section_name = group_dict.get("section", "")
    fallback_id = group_dict.get("fallback_id")
    if fallback_id is None and "fallback" in group_dict:
        fallback_id = _get_fallback_id(conn, group_dict["fallback"])

    topic_id = _get_topic_id(conn, topic_name)
    section_id = _get_section_id(conn, section_name)
    a_count = len(answers)
    now = datetime.datetime.now().isoformat()

    # Fetch old blob IDs to release later
    cur = conn.execute("SELECT questions_blob_id, answers_blob_id FROM groups WHERE id = ?", (group_id,))
    old_q_id, old_a_id = cur.fetchone()

    q_id, a_id = _store_qa_lists(conn, questions, answers)

    try:
        conn.execute(
            """UPDATE groups SET group_name = ?, topic_id = ?, section_id = ?, fallback_id = ?,
               questions_blob_id = ?, answers_blob_id = ?, answer_count = ?, updated_at = ?
               WHERE id = ?""",
            (group_dict["group_name"], topic_id, section_id, fallback_id, q_id, a_id, a_count, now, group_id)
        )
        # Release old blobs after successful update
        release_blob(conn, old_q_id)
        release_blob(conn, old_a_id)

        conn.execute("DELETE FROM group_questions WHERE group_id = ?", (group_id,))
        for idx, q in enumerate(questions):
            qid = _get_or_create_question_id(conn, q)
            conn.execute(
                "INSERT INTO group_questions (group_id, question_id, sort_order) VALUES (?, ?, ?)",
                (group_id, qid, idx)
            )
        delete_followup_tree(conn, group_id)
        if "follow_ups" in group_dict and group_dict["follow_ups"]:
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
    from .helpers import _get_topic_name, _get_section_name, _get_fallback_name
    from .followups import load_followup_tree_full
    cur = conn.execute("""
        SELECT g.id, g.group_name, g.topic_id, g.section_id, g.fallback_id,
               g.questions_blob_id, g.answers_blob_id, g.created_at, g.updated_at
        FROM groups g
        WHERE g.id = ?
    """, (group_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Group id {group_id} not found")
    questions_raw = get_blob_data(conn, row[5])
    answers_raw = get_blob_data(conn, row[6])
    questions = unpack_array(questions_raw) if questions_raw else []
    answers = unpack_array(answers_raw) if answers_raw else []
    group = {
        "id": row[0],
        "group_name": row[1],
        "topic": _get_topic_name(conn, row[2]),
        "section": _get_section_name(conn, row[3]),
        "fallback": _get_fallback_name(conn, row[4]),
        "questions": questions,
        "answers": answers,
        "created_at": row[7],
        "updated_at": row[8]
    }
    if include_followups:
        group["follow_ups"] = load_followup_tree_full(conn, group_id)
    return group

def get_group_summaries(conn: sqlite3.Connection) -> List[Dict]:
    cur = conn.execute("""
        SELECT g.id, g.group_name,
               COALESCE(t.name, '') as topic,
               COALESCE(s.name, '') as section,
               (SELECT GROUP_CONCAT(q.text, '|') FROM group_questions gq JOIN questions q ON gq.question_id = q.id WHERE gq.group_id = g.id ORDER BY gq.sort_order) as questions_text
        FROM groups g
        LEFT JOIN topics t ON g.topic_id = t.id
        LEFT JOIN sections s ON g.section_id = s.id
        ORDER BY g.id
    """)
    summaries = []
    for row in cur:
        summaries.append({
            "id": row[0],
            "group_name": row[1],
            "topic": row[2],
            "section": row[3],
            "questions": row[4].split('|') if row[4] else []
        })
    return summaries

def get_group_summaries_with_counts(conn: sqlite3.Connection) -> List[Dict]:
    cur = conn.execute("""
        SELECT g.id, g.group_name,
               COALESCE(t.name, '') as topic,
               COALESCE(s.name, '') as section,
               (SELECT COUNT(*) FROM group_questions WHERE group_id = g.id) as question_count,
               g.answer_count
        FROM groups g
        LEFT JOIN topics t ON g.topic_id = t.id
        LEFT JOIN sections s ON g.section_id = s.id
        ORDER BY g.id
    """)
    summaries = []
    for row in cur:
        summaries.append({
            "id": row[0],
            "group_name": row[1],
            "topic": row[2],
            "section": row[3],
            "question_count": row[4],
            "answer_count": row[5]
        })
    return summaries