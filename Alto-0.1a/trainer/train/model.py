import sqlite3
import json
import datetime
import time
from collections import OrderedDict
from typing import List, Dict, Optional, Any
from .core import (
    get_model_db_path, pack_array, unpack_array, update_fts_index,
    insert_followup_tree, delete_followup_tree, load_followup_tree_full
)

# ----------------------------------------------------------------------
# Model DB initialization
# ----------------------------------------------------------------------
def init_model_db(conn: sqlite3.Connection, model_name: str, description: str, author: str, version: str):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_info (
            name TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            author TEXT NOT NULL,
            version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sections TEXT NOT NULL,
            topics TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY,
            group_name TEXT NOT NULL,
            topic TEXT NOT NULL,
            section TEXT NOT NULL,
            questions_blob BLOB NOT NULL,
            answers_blob BLOB NOT NULL,
            question_count INTEGER NOT NULL DEFAULT 0,
            answer_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts USING fts5(
            group_id UNINDEXED,
            question
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS followup_nodes (
            id INTEGER PRIMARY KEY,
            group_id INTEGER NOT NULL,
            parent_id INTEGER,
            branch_name TEXT NOT NULL,
            questions_blob BLOB NOT NULL,
            answers_blob BLOB NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_id) REFERENCES followup_nodes(id) ON DELETE CASCADE
        )
    """)
    # Variant tables (normalized)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS variant_groups (
            id INTEGER PRIMARY KEY,
            topic TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS variant_words (
            word TEXT NOT NULL,
            group_id INTEGER NOT NULL REFERENCES variant_groups(id) ON DELETE CASCADE,
            PRIMARY KEY (word, group_id)
        ) WITHOUT ROWID
    """)
    # Routes table (model-specific)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY,
            module_name TEXT NOT NULL,
            variants TEXT NOT NULL   -- JSON array of phrases
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_variant_words_word ON variant_words(word)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_followup_nodes_group_parent ON followup_nodes(group_id, parent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_followup_nodes_parent ON followup_nodes(parent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_section ON groups(section)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_topic ON groups(topic)")

    now = datetime.datetime.now().isoformat()
    sections = json.dumps(["General", "Technical", "Creative"], separators=(',', ':'))
    default_topics = json.dumps(["general", "greeting", "programming", "ai", "gaming", "creative", "thanks"], separators=(',', ':'))
    conn.execute(
        """INSERT INTO model_info
           (name, description, author, version, created_at, updated_at, sections, topics)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (model_name, description, author, version, now, now, sections, default_topics)
    )
    conn.commit()

def get_model_info(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.execute("SELECT name, description, author, version, created_at, updated_at, sections, topics FROM model_info")
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
        "sections": json.loads(row[6]),
        "topics": json.loads(row[7]) if row[7] else []
    }

def update_model_info(conn: sqlite3.Connection, **kwargs):
    info = get_model_info(conn)
    if "description" in kwargs:
        info["description"] = kwargs["description"]
    if "author" in kwargs:
        info["author"] = kwargs["author"]
    if "version" in kwargs:
        info["version"] = kwargs["version"]
    if "topics" in kwargs:
        info["topics"] = kwargs["topics"]
    info["updated_at"] = datetime.datetime.now().isoformat()
    conn.execute(
        """UPDATE model_info
           SET description = ?, author = ?, version = ?, updated_at = ?, sections = ?, topics = ?
           WHERE name = ?""",
        (info["description"], info["author"], info["version"],
         info["updated_at"], json.dumps(info["sections"], separators=(',', ':')),
         json.dumps(info["topics"], separators=(',', ':')), info["name"])
    )
    conn.commit()
    return info

# ----------------------------------------------------------------------
# Group operations
# ----------------------------------------------------------------------
def group_from_row_full(row: sqlite3.Row) -> Dict[str, Any]:
    """Full group with both questions and answers."""
    return {
        "id": row[0],
        "group_name": row[1],
        "topic": row[2],
        "section": row[3],
        "questions": unpack_array(row[4]),
        "answers": unpack_array(row[5]),
    }

def insert_group(conn: sqlite3.Connection, model_name: str, group_dict: Dict[str, Any]) -> int:
    group_dict.setdefault("group_name", "New Group")
    group_dict.setdefault("questions", [])
    group_dict.setdefault("answers", [])
    group_dict.setdefault("topic", "general")
    group_dict.setdefault("section", "")

    questions = group_dict["questions"]
    answers = group_dict["answers"]
    questions_blob = pack_array(questions)
    answers_blob = pack_array(answers)
    q_count = len(questions)
    a_count = len(answers)

    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """INSERT INTO groups (group_name, topic, section, questions_blob, answers_blob, question_count, answer_count)
               VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (group_dict["group_name"], group_dict["topic"], group_dict["section"],
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
    group_dict.setdefault("topic", "general")
    group_dict.setdefault("section", "")

    questions = group_dict["questions"]
    answers = group_dict["answers"]
    questions_blob = pack_array(questions)
    answers_blob = pack_array(answers)
    q_count = len(questions)
    a_count = len(answers)

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """UPDATE groups SET group_name = ?, topic = ?, section = ?,
               questions_blob = ?, answers_blob = ?, question_count = ?, answer_count = ?
               WHERE id = ?""",
            (group_dict["group_name"], group_dict["topic"], group_dict["section"],
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
# Route operations
# ----------------------------------------------------------------------
def get_route_summaries(conn: sqlite3.Connection) -> List[Dict]:
    """Return list of {id, module_name, variant_count}."""
    cur = conn.execute("""
        SELECT id, module_name, json_array_length(variants) as variant_count
        FROM routes
        ORDER BY id
    """)
    return [{"id": row[0], "module_name": row[1], "variant_count": row[2]} for row in cur]

def get_route_full(conn: sqlite3.Connection, route_id: int) -> Dict:
    cur = conn.execute("SELECT id, module_name, variants FROM routes WHERE id = ?", (route_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError("Route not found")
    return {
        "id": row[0],
        "module_name": row[1],
        "variants": json.loads(row[2])
    }

def insert_route(conn: sqlite3.Connection, module_name: str, variants: List[str]) -> int:
    cur = conn.execute(
        "INSERT INTO routes (module_name, variants) VALUES (?, ?) RETURNING id",
        (module_name, json.dumps(variants))
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to retrieve inserted route ID")
    conn.commit()
    return row[0]

def update_route(conn: sqlite3.Connection, route_id: int, module_name: str, variants: List[str]):
    conn.execute(
        "UPDATE routes SET module_name = ?, variants = ? WHERE id = ?",
        (module_name, json.dumps(variants), route_id)
    )
    conn.commit()

def delete_route(conn: sqlite3.Connection, route_id: int):
    conn.execute("DELETE FROM routes WHERE id = ?", (route_id,))
    conn.commit()

# ----------------------------------------------------------------------
# Model class (caches summaries only)
# ----------------------------------------------------------------------
class Model:
    def __init__(self, name: str):
        self.name = name
        db_path = get_model_db_path(name)
        if not db_path:
            raise FileNotFoundError(f"Model '{name}' not found")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        # Reduce memory cache size to 5MB (from 20MB)
        self.conn.execute("PRAGMA cache_size = -5000")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA mmap_size = 30000000000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row

        # No migration helpers – we assume the database schema is up‑to‑date.
        self._group_summaries = None
        self.last_used = time.time()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _load_group_summaries(self):
        cur = self.conn.execute(
            "SELECT id, group_name, topic, section FROM groups ORDER BY id"
        )
        self._group_summaries = [dict(row) for row in cur]

    def get_group_summaries(self) -> List[Dict]:
        self.last_used = time.time()
        if self._group_summaries is None:
            self._load_group_summaries()
        return self._group_summaries

    def get_group_summaries_with_counts(self) -> List[Dict]:
        """Return summaries with question and answer counts (using stored counts)."""
        self.last_used = time.time()
        cur = self.conn.execute(
            """SELECT id, group_name, topic, section,
                      question_count, answer_count
               FROM groups ORDER BY id"""
        )
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
        info = get_model_info(self.conn)
        return info["sections"]

    def get_group_by_id(self, group_id: int, include_followups: bool = False) -> Dict:
        """Get a group. If include_followups is False, the follow‑up tree is not loaded."""
        self.last_used = time.time()
        cur = self.conn.execute(
            "SELECT id, group_name, topic, section, "
            "questions_blob, answers_blob FROM groups WHERE id = ?",
            (group_id,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Group id {group_id} not found")
        group = group_from_row_full(row)
        if include_followups:
            group["follow_ups"] = load_followup_tree_full(self.conn, group_id)
        return group

    def _validate_topic(self, topic: str):
        """Allow empty string (no topic), otherwise check against topics list."""
        if topic == "":
            return
        topics = self.get_topics()
        if topic not in topics:
            raise ValueError(f"Topic '{topic}' is not in model's topics list")

    def insert_group(self, group_dict: Dict) -> int:
        self.last_used = time.time()
        self._validate_topic(group_dict.get("topic", "general"))
        group_id = insert_group(self.conn, self.name, group_dict)
        self._group_summaries = None
        return group_id

    def update_group(self, group_id: int, group_dict: Dict):
        self.last_used = time.time()
        self._validate_topic(group_dict.get("topic", "general"))
        update_group(self.conn, group_id, group_dict)
        self._group_summaries = None

    def delete_group(self, group_id: int):
        self.last_used = time.time()
        delete_group(self.conn, group_id)
        self._group_summaries = None

    def get_topics(self) -> List[str]:
        self.last_used = time.time()
        cur = self.conn.execute("SELECT topics FROM model_info")
        row = cur.fetchone()
        if not row:
            return []
        return json.loads(row[0])

    def update_topics(self, topics: List[str]):
        self.last_used = time.time()
        info = get_model_info(self.conn)
        info["updated_at"] = datetime.datetime.now().isoformat()
        self.conn.execute(
            "UPDATE model_info SET topics = ?, updated_at = ? WHERE name = ?",
            (json.dumps(topics, separators=(',', ':')), info["updated_at"], self.name)
        )
        self.conn.commit()

    def get_variants(self) -> List[Dict]:
        """Return all variant groups (id, topic, words)."""
        self.last_used = time.time()
        cur = self.conn.execute("""
            SELECT g.id, g.topic, GROUP_CONCAT(w.word, ',') as words
            FROM variant_groups g
            LEFT JOIN variant_words w ON w.group_id = g.id
            GROUP BY g.id
            ORDER BY g.id
        """)
        variants = []
        for row in cur:
            words = row[2].split(',') if row[2] else []
            variants.append({"id": row[0], "topic": row[1], "words": words})
        return variants

    # ----- Routes -----
    def get_route_summaries(self) -> List[Dict]:
        self.last_used = time.time()
        return get_route_summaries(self.conn)

    def get_route_full(self, index: int) -> Dict:
        """Get full route by index (order by id)."""
        self.last_used = time.time()
        summaries = self.get_route_summaries()
        if index < 0 or index >= len(summaries):
            raise IndexError("Route index out of range")
        route_id = summaries[index]["id"]
        return get_route_full(self.conn, route_id)

    def add_route(self, module_name: str, variants: List[str]) -> int:
        self.last_used = time.time()
        return insert_route(self.conn, module_name, variants)

    def update_route(self, index: int, module_name: str, variants: List[str]):
        self.last_used = time.time()
        summaries = self.get_route_summaries()
        if index < 0 or index >= len(summaries):
            raise IndexError("Route index out of range")
        route_id = summaries[index]["id"]
        update_route(self.conn, route_id, module_name, variants)

    def delete_route(self, index: int):
        self.last_used = time.time()
        summaries = self.get_route_summaries()
        if index < 0 or index >= len(summaries):
            raise IndexError("Route index out of range")
        route_id = summaries[index]["id"]
        delete_route(self.conn, route_id)

# ----------------------------------------------------------------------
# Global model cache with LRU eviction
# ----------------------------------------------------------------------
_model_cache: OrderedDict[str, Model] = OrderedDict()
MAX_CACHED_MODELS = 3

def get_model(name: str) -> Model:
    global _model_cache
    if name in _model_cache:
        model = _model_cache.pop(name)  # remove to reinsert at end
        model.last_used = time.time()
        _model_cache[name] = model
        return model
    else:
        model = Model(name)
        # If cache full, evict oldest (first item)
        if len(_model_cache) >= MAX_CACHED_MODELS:
            oldest_name, oldest_model = _model_cache.popitem(last=False)
            oldest_model.close()
        _model_cache[name] = model
        return model

def close_all_models():
    for model in _model_cache.values():
        model.close()
    _model_cache.clear()