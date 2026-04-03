import sqlite3
import json
import datetime
import time
from collections import OrderedDict
from typing import List, Dict, Optional, Any
from train.utils.file_helpers import get_model_db_path
from train.utils.msgpack_helpers import pack_array, unpack_array
from train.utils.fts_helpers import update_fts_index
from train.groups.utils import (
    insert_followup_tree, delete_followup_tree, load_followup_tree_full
)

# --- Version constant for this trainer release ---
ALTO_VERSION = "0.2a"

# ----------------------------------------------------------------------
# Model DB initialization (new schema)
# ----------------------------------------------------------------------
def init_model_db(conn: sqlite3.Connection, model_name: str, description: str, author: str, version: str):
    # Model info
    conn.execute("""
        CREATE TABLE model_info (
            name TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            author TEXT NOT NULL,
            version TEXT NOT NULL,
            alto_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Sections table
    conn.execute("""
        CREATE TABLE sections (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Topics table (with optional section)
    conn.execute("""
        CREATE TABLE topics (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL
        )
    """)

    # Groups table (references topic and section by ID)
    conn.execute("""
        CREATE TABLE groups (
            id INTEGER PRIMARY KEY,
            group_name TEXT NOT NULL,
            topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
            section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
            questions_blob BLOB NOT NULL,
            answers_blob BLOB NOT NULL,
            question_count INTEGER NOT NULL DEFAULT 0,
            answer_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    # FTS for questions
    conn.execute("""
        CREATE VIRTUAL TABLE questions_fts USING fts5(
            group_id UNINDEXED,
            question
        )
    """)

    # Follow-up nodes
    conn.execute("""
        CREATE TABLE followup_nodes (
            id INTEGER PRIMARY KEY,
            group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            parent_id INTEGER REFERENCES followup_nodes(id) ON DELETE CASCADE,
            branch_name TEXT NOT NULL,
            questions_blob BLOB NOT NULL,
            answers_blob BLOB NOT NULL
        )
    """)

    # Variant groups (with name and section_id only)
    conn.execute("""
        CREATE TABLE variant_groups (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Variant words
    conn.execute("""
        CREATE TABLE variant_words (
            word TEXT NOT NULL,
            group_id INTEGER NOT NULL REFERENCES variant_groups(id) ON DELETE CASCADE,
            PRIMARY KEY (word, group_id)
        ) WITHOUT ROWID
    """)

    # Indexes
    conn.execute("CREATE INDEX idx_groups_topic ON groups(topic_id)")
    conn.execute("CREATE INDEX idx_groups_section ON groups(section_id)")
    conn.execute("CREATE INDEX idx_topics_section ON topics(section_id)")
    conn.execute("CREATE INDEX idx_variant_groups_section ON variant_groups(section_id)")
    conn.execute("CREATE INDEX idx_variant_words_word ON variant_words(word)")
    conn.execute("CREATE INDEX idx_followup_nodes_group_parent ON followup_nodes(group_id, parent_id)")
    conn.execute("CREATE INDEX idx_followup_nodes_parent ON followup_nodes(parent_id)")

    # Insert default sections
    default_sections = ["General", "Technical", "Creative"]
    for idx, name in enumerate(default_sections):
        conn.execute("INSERT INTO sections (name, sort_order) VALUES (?, ?)", (name, idx))

    # Insert default topics (each assigned to the "General" section initially)
    general_section_id = conn.execute("SELECT id FROM sections WHERE name = 'General'").fetchone()[0]
    default_topics = ["general", "greeting", "programming", "ai", "gaming", "creative", "thanks"]
    for name in default_topics:
        conn.execute(
            "INSERT INTO topics (name, section_id) VALUES (?, ?)",
            (name, general_section_id)
        )

    # Insert model info with alto_version
    now = datetime.datetime.now().isoformat()
    conn.execute(
        """INSERT INTO model_info
           (name, description, author, version, alto_version, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (model_name, description, author, version, ALTO_VERSION, now, now)
    )
    conn.commit()

def get_model_info(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.execute("SELECT name, description, author, version, alto_version, created_at, updated_at FROM model_info")
    row = cur.fetchone()
    if not row:
        raise ValueError("Model info not found")

    # Fetch sections as list of names ordered by sort_order
    cur = conn.execute("SELECT name FROM sections ORDER BY sort_order")
    sections = [r[0] for r in cur]

    # Fetch topics as list of names
    cur = conn.execute("SELECT name FROM topics ORDER BY name")
    topics = [r[0] for r in cur]

    return {
        "name": row[0],
        "description": row[1],
        "author": row[2],
        "version": row[3],
        "alto_version": row[4],
        "created_at": row[5],
        "updated_at": row[6],
        "sections": sections,
        "topics": topics
    }

def update_model_info(conn: sqlite3.Connection, **kwargs):
    info = get_model_info(conn)
    if "description" in kwargs:
        info["description"] = kwargs["description"]
    if "author" in kwargs:
        info["author"] = kwargs["author"]
    if "version" in kwargs:
        info["version"] = kwargs["version"]
    # alto_version is not updated
    info["updated_at"] = datetime.datetime.now().isoformat()
    conn.execute(
        """UPDATE model_info
           SET description = ?, author = ?, version = ?, updated_at = ?
           WHERE name = ?""",
        (info["description"], info["author"], info["version"],
         info["updated_at"], info["name"])
    )
    conn.commit()
    return info

# ----------------------------------------------------------------------
# Helper to resolve topic name to ID
# ----------------------------------------------------------------------
def _get_topic_id(conn: sqlite3.Connection, topic_name: str) -> Optional[int]:
    if not topic_name:
        return None
    cur = conn.execute("SELECT id FROM topics WHERE name = ?", (topic_name,))
    row = cur.fetchone()
    return row[0] if row else None

def _get_section_id(conn: sqlite3.Connection, section_name: str) -> Optional[int]:
    if not section_name:
        return None
    cur = conn.execute("SELECT id FROM sections WHERE name = ?", (section_name,))
    row = cur.fetchone()
    return row[0] if row else None

def _get_topic_name(conn: sqlite3.Connection, topic_id: Optional[int]) -> str:
    if topic_id is None:
        return ""
    cur = conn.execute("SELECT name FROM topics WHERE id = ?", (topic_id,))
    row = cur.fetchone()
    return row[0] if row else ""

def _get_section_name(conn: sqlite3.Connection, section_id: Optional[int]) -> str:
    if section_id is None:
        return ""
    cur = conn.execute("SELECT name FROM sections WHERE id = ?", (section_id,))
    row = cur.fetchone()
    return row[0] if row else ""

# ----------------------------------------------------------------------
# Group operations
# ----------------------------------------------------------------------
def group_from_row_full(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row[0],
        "group_name": row[1],
        "topic": _get_topic_name(row[2]),
        "section": _get_section_name(row[3]),
        "questions": unpack_array(row[4]),
        "answers": unpack_array(row[5]),
    }

def insert_group(conn: sqlite3.Connection, model_name: str, group_dict: Dict[str, Any]) -> int:
    group_dict.setdefault("group_name", "New Group")
    group_dict.setdefault("questions", [])
    group_dict.setdefault("answers", [])
    topic_name = group_dict.get("topic", "")
    section_name = group_dict.get("section", "")

    topic_id = _get_topic_id(conn, topic_name)
    section_id = _get_section_id(conn, section_name)

    questions = group_dict["questions"]
    answers = group_dict["answers"]
    questions_blob = pack_array(questions)
    answers_blob = pack_array(answers)
    q_count = len(questions)
    a_count = len(answers)

    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """INSERT INTO groups (group_name, topic_id, section_id, questions_blob, answers_blob, question_count, answer_count)
               VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (group_dict["group_name"], topic_id, section_id,
             questions_blob, answers_blob, q_count, a_count)
        )
        group_id = cursor.fetchone()[0]
        update_fts_index(conn, group_id, questions)
        if "follow_ups" in group_dict and group_dict["follow_ups"]:
            insert_followup_tree(conn, group_id, group_dict["follow_ups"])
        conn.commit()
        return group_id
    except Exception:
        conn.rollback()
        raise

def update_group(conn: sqlite3.Connection, group_id: int, group_dict: Dict[str, Any]):
    group_dict.setdefault("group_name", "New Group")
    group_dict.setdefault("questions", [])
    group_dict.setdefault("answers", [])
    topic_name = group_dict.get("topic", "")
    section_name = group_dict.get("section", "")

    topic_id = _get_topic_id(conn, topic_name)
    section_id = _get_section_id(conn, section_name)

    questions = group_dict["questions"]
    answers = group_dict["answers"]
    questions_blob = pack_array(questions)
    answers_blob = pack_array(answers)
    q_count = len(questions)
    a_count = len(answers)

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """UPDATE groups SET group_name = ?, topic_id = ?, section_id = ?,
               questions_blob = ?, answers_blob = ?, question_count = ?, answer_count = ?
               WHERE id = ?""",
            (group_dict["group_name"], topic_id, section_id,
             questions_blob, answers_blob, q_count, a_count, group_id)
        )
        update_fts_index(conn, group_id, questions)
        delete_followup_tree(conn, group_id)
        if "follow_ups" in group_dict and group_dict["follow_ups"]:
            insert_followup_tree(conn, group_id, group_dict["follow_ups"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def delete_group(conn: sqlite3.Connection, group_id: int):
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
# Model class
# ----------------------------------------------------------------------
class Model:
    def __init__(self, name: str):
        self.name = name
        db_path = get_model_db_path(name)
        if not db_path:
            raise FileNotFoundError(f"Model '{name}' not found")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA cache_size = -5000")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA mmap_size = 30000000000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row

        self._group_summaries = None
        self.last_used = time.time()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _load_group_summaries(self):
        cur = self.conn.execute("""
            SELECT g.id, g.group_name,
                   COALESCE(t.name, '') as topic,
                   COALESCE(s.name, '') as section
            FROM groups g
            LEFT JOIN topics t ON g.topic_id = t.id
            LEFT JOIN sections s ON g.section_id = s.id
            ORDER BY g.id
        """)
        self._group_summaries = [dict(row) for row in cur]

    def get_group_summaries(self) -> List[Dict]:
        self.last_used = time.time()
        if self._group_summaries is None:
            self._load_group_summaries()
        return self._group_summaries

    def get_group_summaries_with_counts(self) -> List[Dict]:
        self.last_used = time.time()
        cur = self.conn.execute("""
            SELECT g.id, g.group_name,
                   COALESCE(t.name, '') as topic,
                   COALESCE(s.name, '') as section,
                   g.question_count, g.answer_count
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

    def get_sections(self) -> List[str]:
        self.last_used = time.time()
        cur = self.conn.execute("SELECT name FROM sections ORDER BY sort_order")
        return [row[0] for row in cur]

    def get_topics(self) -> List[str]:
        self.last_used = time.time()
        cur = self.conn.execute("SELECT name FROM topics ORDER BY name")
        return [row[0] for row in cur]

    def get_group_by_id(self, group_id: int, include_followups: bool = False) -> Dict:
        self.last_used = time.time()
        cur = self.conn.execute("""
            SELECT g.id, g.group_name, g.topic_id, g.section_id,
                   g.questions_blob, g.answers_blob
            FROM groups g
            WHERE g.id = ?
        """, (group_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Group id {group_id} not found")
        group = {
            "id": row[0],
            "group_name": row[1],
            "topic": _get_topic_name(self.conn, row[2]),
            "section": _get_section_name(self.conn, row[3]),
            "questions": unpack_array(row[4]),
            "answers": unpack_array(row[5])
        }
        if include_followups:
            group["follow_ups"] = load_followup_tree_full(self.conn, group_id)
        return group

    def insert_group(self, group_dict: Dict) -> int:
        self.last_used = time.time()
        group_id = insert_group(self.conn, self.name, group_dict)
        self._group_summaries = None
        return group_id

    def update_group(self, group_id: int, group_dict: Dict):
        self.last_used = time.time()
        update_group(self.conn, group_id, group_dict)
        self._group_summaries = None

    def delete_group(self, group_id: int):
        self.last_used = time.time()
        delete_group(self.conn, group_id)
        self._group_summaries = None

    # ----- Section management -----
    def add_section(self, name: str) -> int:
        self.last_used = time.time()
        max_order = self.conn.execute("SELECT COALESCE(MAX(sort_order), -1) FROM sections").fetchone()[0]
        cursor = self.conn.execute(
            "INSERT INTO sections (name, sort_order) VALUES (?, ?) RETURNING id",
            (name, max_order + 1)
        )
        self.conn.commit()
        return cursor.fetchone()[0]

    def rename_section(self, old_name: str, new_name: str):
        self.last_used = time.time()
        self.conn.execute("UPDATE sections SET name = ? WHERE name = ?", (new_name, old_name))
        self.conn.commit()

    def delete_section(self, name: str, action: str = "uncategorized", target: Optional[str] = None):
        self.last_used = time.time()
        section_id = _get_section_id(self.conn, name)
        if not section_id:
            raise ValueError(f"Section '{name}' not found")

        target_id = None
        if target:
            target_id = _get_section_id(self.conn, target)
            if not target_id:
                raise ValueError(f"Target section '{target}' not found")

        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            if action == "uncategorized":
                # Set section_id to NULL for groups, topics, variants
                conn.execute("UPDATE groups SET section_id = NULL WHERE section_id = ?", (section_id,))
                conn.execute("UPDATE topics SET section_id = NULL WHERE section_id = ?", (section_id,))
                conn.execute("UPDATE variant_groups SET section_id = NULL WHERE section_id = ?", (section_id,))
            elif action == "move":
                if target_id is None:
                    raise ValueError("Target section required for move action")
                conn.execute("UPDATE groups SET section_id = ? WHERE section_id = ?", (target_id, section_id))
                conn.execute("UPDATE topics SET section_id = ? WHERE section_id = ?", (target_id, section_id))
                conn.execute("UPDATE variant_groups SET section_id = ? WHERE section_id = ?", (target_id, section_id))
            elif action == "delete":
                # Delete all groups in this section (cascades to followups, FTS)
                cur = conn.execute("SELECT id FROM groups WHERE section_id = ?", (section_id,))
                for row in cur:
                    delete_group(conn, row[0])
                conn.execute("UPDATE topics SET section_id = NULL WHERE section_id = ?", (section_id,))
                conn.execute("UPDATE variant_groups SET section_id = NULL WHERE section_id = ?", (section_id,))
            else:
                raise ValueError(f"Invalid action: {action}")

            # Delete the section itself
            conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ----- Topic management -----
    def add_topic(self, name: str, section_name: Optional[str] = None) -> int:
        self.last_used = time.time()
        section_id = _get_section_id(self.conn, section_name) if section_name else None
        cursor = self.conn.execute(
            "INSERT INTO topics (name, section_id) VALUES (?, ?) RETURNING id",
            (name, section_id)
        )
        self.conn.commit()
        return cursor.fetchone()[0]

    def rename_topic(self, old_name: str, new_name: str):
        self.last_used = time.time()
        self.conn.execute("UPDATE topics SET name = ? WHERE name = ?", (new_name, old_name))
        self.conn.commit()

    def delete_topic(self, name: str, action: str = "reassign", target: Optional[str] = None):
        self.last_used = time.time()
        topic_id = _get_topic_id(self.conn, name)
        if not topic_id:
            raise ValueError(f"Topic '{name}' not found")

        target_id = None
        if target:
            target_id = _get_topic_id(self.conn, target)
            if not target_id:
                raise ValueError(f"Target topic '{target}' not found")

        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            if action == "reassign":
                # Move groups to target topic (or NULL)
                conn.execute("UPDATE groups SET topic_id = ? WHERE topic_id = ?", (target_id, topic_id))
            elif action == "delete_groups":
                # Delete all groups using this topic
                cur = conn.execute("SELECT id FROM groups WHERE topic_id = ?", (topic_id,))
                for row in cur:
                    delete_group(conn, row[0])
            else:
                raise ValueError(f"Invalid action: {action}")

            # Delete the topic itself
            conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_topic_groups(self, topic_name: str) -> List[Dict]:
        self.last_used = time.time()
        topic_id = _get_topic_id(self.conn, topic_name)
        if not topic_id:
            return []
        cur = self.conn.execute("""
            SELECT g.id, g.group_name, g.question_count, g.answer_count,
                   COALESCE(s.name, '') as section
            FROM groups g
            LEFT JOIN sections s ON g.section_id = s.id
            WHERE g.topic_id = ?
            ORDER BY g.id
        """, (topic_id,))
        groups = []
        for row in cur:
            groups.append({
                "id": row[0],
                "group_name": row[1],
                "question_count": row[2],
                "answer_count": row[3],
                "section": row[4]
            })
        return groups

    # ----- Variant management (with name) -----
    def get_variants(self) -> List[Dict]:
        self.last_used = time.time()
        cur = self.conn.execute("""
            SELECT vg.id, vg.name,
                   COALESCE(s.name, '') as section,
                   GROUP_CONCAT(vw.word, ',') as words
            FROM variant_groups vg
            LEFT JOIN sections s ON vg.section_id = s.id
            LEFT JOIN variant_words vw ON vw.group_id = vg.id
            GROUP BY vg.id
            ORDER BY vg.id
        """)
        variants = []
        for row in cur:
            words = row[3].split(',') if row[3] else []
            variants.append({
                "id": row[0],
                "name": row[1],
                "section": row[2],
                "words": words
            })
        return variants

    def add_variant(self, name: str, section_name: Optional[str], words: List[str]) -> int:
        self.last_used = time.time()
        section_id = _get_section_id(self.conn, section_name) if section_name else None
        now = datetime.datetime.now().isoformat()
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "INSERT INTO variant_groups (name, section_id, created_at) VALUES (?, ?, ?) RETURNING id",
                (name, section_id, now)
            )
            group_id = cur.fetchone()[0]
            for word in words:
                conn.execute(
                    "INSERT INTO variant_words (word, group_id) VALUES (?, ?)",
                    (word, group_id)
                )
            conn.commit()
            return group_id
        except Exception:
            conn.rollback()
            raise

    def update_variant(self, variant_id: int, name: str, section_name: Optional[str], words: List[str]):
        self.last_used = time.time()
        section_id = _get_section_id(self.conn, section_name) if section_name else None
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE variant_groups SET name = ?, section_id = ? WHERE id = ?",
                (name, section_id, variant_id)
            )
            conn.execute("DELETE FROM variant_words WHERE group_id = ?", (variant_id,))
            for word in words:
                conn.execute(
                    "INSERT INTO variant_words (word, group_id) VALUES (?, ?)",
                    (word, variant_id)
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def delete_variant(self, variant_id: int):
        self.last_used = time.time()
        self.conn.execute("DELETE FROM variant_groups WHERE id = ?", (variant_id,))
        self.conn.commit()

# ----------------------------------------------------------------------
# Global model cache
# ----------------------------------------------------------------------
_model_cache: OrderedDict[str, Model] = OrderedDict()
MAX_CACHED_MODELS = 3

def get_model(name: str) -> Model:
    global _model_cache
    if name in _model_cache:
        model = _model_cache.pop(name)
        model.last_used = time.time()
        _model_cache[name] = model
        return model
    else:
        model = Model(name)
        if len(_model_cache) >= MAX_CACHED_MODELS:
            oldest_name, oldest_model = _model_cache.popitem(last=False)
            oldest_model.close()
        _model_cache[name] = model
        return model

def close_all_models():
    for model in _model_cache.values():
        model.close()
    _model_cache.clear()