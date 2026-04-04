import sqlite3
import datetime
import time
import shutil
import tempfile
import os
import zlib
from collections import OrderedDict
from typing import List, Dict, Optional, Any
from train.utils.file_helpers import (
    get_model_db_path, find_model_dir, safe_filename, MODELS_BASE_DIR,
    get_model_container_path, get_model_temp_dir, pack_model, unpack_model
)
from train.utils.msgpack_helpers import pack_array, unpack_array
from train.groups.utils import (
    insert_followup_tree, delete_followup_tree, load_followup_tree_full
)

ALTO_VERSION = "0.2a"

# ----------------------------------------------------------------------
# Compression helpers
# ----------------------------------------------------------------------
def compress_blob(data: bytes) -> bytes:
    return zlib.compress(data, level=6)

def decompress_blob(data: bytes) -> bytes:
    return zlib.decompress(data)

# ----------------------------------------------------------------------
# Schema creation
# ----------------------------------------------------------------------
def create_empty_schema(conn: sqlite3.Connection):
    """Create all tables and indexes without default data."""
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
    conn.execute("""
        CREATE TABLE sections (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE topics (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL
        )
    """)
    conn.execute("""
        CREATE TABLE groups (
            id INTEGER PRIMARY KEY,
            group_name TEXT NOT NULL,
            topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
            section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
            answers_blob BLOB NOT NULL,
            answer_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY,
            text TEXT NOT NULL UNIQUE
        )
    """)
    conn.execute("""
        CREATE TABLE group_questions (
            group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (group_id, question_id)
        ) WITHOUT ROWID
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE questions_fts USING fts5(
            content=questions,
            content_rowid=id,
            text
        )
    """)
    conn.execute("""
        CREATE TRIGGER questions_ai AFTER INSERT ON questions BEGIN
            INSERT INTO questions_fts(rowid, text) VALUES (new.id, new.text);
        END
    """)
    conn.execute("""
        CREATE TRIGGER questions_ad AFTER DELETE ON questions BEGIN
            INSERT INTO questions_fts(questions_fts, rowid, text) VALUES('delete', old.id, old.text);
        END
    """)
    conn.execute("""
        CREATE TRIGGER questions_au AFTER UPDATE OF text ON questions BEGIN
            INSERT INTO questions_fts(questions_fts, rowid, text) VALUES('delete', old.id, old.text);
            INSERT INTO questions_fts(rowid, text) VALUES (new.id, new.text);
        END
    """)
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
    conn.execute("""
        CREATE TABLE variant_groups (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE variant_words (
            word TEXT NOT NULL,
            group_id INTEGER NOT NULL REFERENCES variant_groups(id) ON DELETE CASCADE,
            PRIMARY KEY (word, group_id)
        ) WITHOUT ROWID
    """)

    conn.execute("CREATE INDEX idx_groups_topic ON groups(topic_id)")
    conn.execute("CREATE INDEX idx_groups_section ON groups(section_id)")
    conn.execute("CREATE INDEX idx_topics_section ON topics(section_id)")
    conn.execute("CREATE INDEX idx_variant_groups_section ON variant_groups(section_id)")
    conn.execute("CREATE INDEX idx_variant_words_word ON variant_words(word)")
    conn.execute("CREATE INDEX idx_followup_nodes_group_parent ON followup_nodes(group_id, parent_id)")
    conn.execute("CREATE INDEX idx_followup_nodes_parent ON followup_nodes(parent_id)")
    conn.execute("CREATE INDEX idx_group_questions_group ON group_questions(group_id)")
    conn.execute("CREATE INDEX idx_group_questions_question ON group_questions(question_id)")

def init_model_db(conn: sqlite3.Connection, model_name: str, description: str, author: str, version: str):
    """Create full schema with default sections/topics for a new model."""
    create_empty_schema(conn)

    default_sections = ["General", "Technical", "Creative"]
    for idx, name in enumerate(default_sections):
        conn.execute("INSERT INTO sections (name, sort_order) VALUES (?, ?)", (name, idx))

    general_section_id = conn.execute("SELECT id FROM sections WHERE name = 'General'").fetchone()[0]
    default_topics = ["general", "greeting", "programming", "ai", "gaming", "creative", "thanks"]
    for name in default_topics:
        conn.execute("INSERT INTO topics (name, section_id) VALUES (?, ?)", (name, general_section_id))

    now = datetime.datetime.now().isoformat()
    conn.execute(
        """INSERT INTO model_info
           (name, description, author, version, alto_version, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (model_name, description, author, version, ALTO_VERSION, now, now)
    )
    conn.commit()

# ----------------------------------------------------------------------
# Helper: get or create question ID
# ----------------------------------------------------------------------
def _get_or_create_question_id(conn: sqlite3.Connection, question_text: str) -> int:
    cur = conn.execute("SELECT id FROM questions WHERE text = ?", (question_text,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO questions (text) VALUES (?) RETURNING id", (question_text,))
    return cur.fetchone()[0]

# ----------------------------------------------------------------------
# Group operations with normalized questions
# ----------------------------------------------------------------------
def insert_group(conn: sqlite3.Connection, model_name: str, group_dict: Dict[str, Any]) -> int:
    group_dict.setdefault("group_name", "New Group")
    questions = group_dict.get("questions", [])
    answers = group_dict.get("answers", [])
    topic_name = group_dict.get("topic", "")
    section_name = group_dict.get("section", "")

    topic_id = _get_topic_id(conn, topic_name)
    section_id = _get_section_id(conn, section_name)

    answers_blob = pack_array(answers)
    compressed_answers = compress_blob(answers_blob)
    a_count = len(answers)
    now = datetime.datetime.now().isoformat()

    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """INSERT INTO groups (group_name, topic_id, section_id, answers_blob, answer_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (group_dict["group_name"], topic_id, section_id, compressed_answers, a_count, now, now)
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

    topic_id = _get_topic_id(conn, topic_name)
    section_id = _get_section_id(conn, section_name)
    answers_blob = pack_array(answers)
    compressed_answers = compress_blob(answers_blob)
    a_count = len(answers)
    now = datetime.datetime.now().isoformat()

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """UPDATE groups SET group_name = ?, topic_id = ?, section_id = ?,
               answers_blob = ?, answer_count = ?, updated_at = ?
               WHERE id = ?""",
            (group_dict["group_name"], topic_id, section_id, compressed_answers, a_count, now, group_id)
        )
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
    conn.execute("DELETE FROM followup_nodes WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))

# ----------------------------------------------------------------------
# Helper functions (unchanged)
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

def get_model_info(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.execute("SELECT name, description, author, version, alto_version, created_at, updated_at FROM model_info")
    row = cur.fetchone()
    if not row:
        raise ValueError("Model info not found")
    cur = conn.execute("SELECT name FROM sections ORDER BY sort_order")
    sections = [r[0] for r in cur]
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
# Model class
# ----------------------------------------------------------------------
class Model:
    def __init__(self, name: str):
        self.name = name
        self.container_path = get_model_container_path(name)
        self.temp_dir = get_model_temp_dir(name)
        self.db_path = None

        if self.container_path:
            self.db_path, manifest = unpack_model(self.container_path, self.temp_dir)
            # Check if this container uses the old schema (missing group_questions)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='group_questions'")
            if cursor.fetchone() is None:
                # Old schema – check version
                cur = conn.execute("SELECT alto_version FROM model_info")
                row = cur.fetchone()
                version = row[0] if row else "0.1a"
                conn.close()
                if version.startswith("0.1"):
                    # Auto‑convert 0.1a models
                    self._migrate_legacy_container(self.db_path, manifest)
                    # Re‑unpack the new container
                    self.db_path, manifest = unpack_model(self.container_path, self.temp_dir)
                else:
                    conn.close()
                    raise RuntimeError(f"Model '{name}' uses an unsupported schema.")
            else:
                conn.close()
        else:
            legacy_db_path = get_model_db_path(name)
            if legacy_db_path and os.path.isfile(legacy_db_path):
                # Legacy folder – assume 0.1a, convert
                self._migrate_legacy_folder(legacy_db_path)
                self.container_path = get_model_container_path(name)
                self.db_path, manifest = unpack_model(self.container_path, self.temp_dir)
            else:
                raise FileNotFoundError(f"Model '{name}' not found")

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA cache_size = -5000")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA mmap_size = 30000000000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row

        self._group_summaries = None
        self.last_used = time.time()

    def _migrate_legacy_container(self, old_db_path: str, old_manifest: dict):
        """Convert an old‑schema .rbm container (0.1a) to the new schema."""
        new_db_path = os.path.join(self.temp_dir, "new_database.db")
        new_conn = sqlite3.connect(new_db_path)
        create_empty_schema(new_conn)

        new_conn.execute(f"ATTACH DATABASE '{old_db_path}' AS old")

        # Copy sections, topics, variants
        for table in ['sections', 'topics', 'variant_groups', 'variant_words']:
            new_conn.execute(f"INSERT INTO {table} SELECT * FROM old.{table}")

        # Copy groups with migration
        now_iso = datetime.datetime.now().isoformat()
        cur = new_conn.execute("SELECT id, group_name, topic_id, section_id, questions_blob, answers_blob FROM old.groups")
        for row in cur:
            gid, gname, tid, sid, q_blob, a_blob = row
            questions = unpack_array(q_blob)
            answers = unpack_array(a_blob)
            answers_compressed = compress_blob(pack_array(answers))
            new_conn.execute(
                """INSERT INTO groups
                   (id, group_name, topic_id, section_id, answers_blob, answer_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (gid, gname, tid, sid, answers_compressed, len(answers), now_iso, now_iso)
            )
            for idx, q in enumerate(questions):
                qid = _get_or_create_question_id(new_conn, q)
                new_conn.execute(
                    "INSERT INTO group_questions (group_id, question_id, sort_order) VALUES (?, ?, ?)",
                    (gid, qid, idx)
                )

        new_conn.execute("INSERT INTO followup_nodes SELECT * FROM old.followup_nodes")

        # Copy model_info from manifest
        name = old_manifest.get("name", self.name)
        desc = old_manifest.get("description", "")
        author = old_manifest.get("author", "")
        version = old_manifest.get("version", "1.0.0")
        alto_ver = old_manifest.get("alto_version", "0.1a")
        created = old_manifest.get("created_at", now_iso)
        updated = old_manifest.get("updated_at", now_iso)
        new_conn.execute(
            """INSERT INTO model_info
               (name, description, author, version, alto_version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, desc, author, version, alto_ver, created, updated)
        )

        new_conn.execute("DETACH old")
        new_conn.commit()
        new_conn.close()

        # Replace the old .rbm
        new_manifest = get_model_info(sqlite3.connect(new_db_path))
        folder = find_model_dir(self.name)
        safe = safe_filename(self.name)
        new_container_path = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.rbm")
        fd, tmp_path = tempfile.mkstemp(suffix='.rbm', dir=os.path.dirname(new_container_path))
        os.close(fd)
        try:
            pack_model(new_db_path, new_manifest, tmp_path)
            os.replace(tmp_path, new_container_path)
            os.remove(old_db_path)
            self.container_path = new_container_path
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _migrate_legacy_folder(self, legacy_db_path: str):
        """Convert a legacy .db folder (0.1a) to the new schema."""
        temp_conn = sqlite3.connect(legacy_db_path)
        temp_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        temp_conn.close()

        new_db_path = os.path.join(self.temp_dir, "new_database.db")
        new_conn = sqlite3.connect(new_db_path)
        create_empty_schema(new_conn)

        new_conn.execute(f"ATTACH DATABASE '{legacy_db_path}' AS old")

        for table in ['sections', 'topics', 'variant_groups', 'variant_words']:
            new_conn.execute(f"INSERT INTO {table} SELECT * FROM old.{table}")

        now_iso = datetime.datetime.now().isoformat()
        cur = new_conn.execute("SELECT id, group_name, topic_id, section_id, questions_blob, answers_blob FROM old.groups")
        for row in cur:
            gid, gname, tid, sid, q_blob, a_blob = row
            questions = unpack_array(q_blob)
            answers = unpack_array(a_blob)
            answers_compressed = compress_blob(pack_array(answers))
            new_conn.execute(
                "INSERT INTO groups (id, group_name, topic_id, section_id, answers_blob, answer_count, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (gid, gname, tid, sid, answers_compressed, len(answers), now_iso, now_iso)
            )
            for idx, q in enumerate(questions):
                qid = _get_or_create_question_id(new_conn, q)
                new_conn.execute("INSERT INTO group_questions (group_id, question_id, sort_order) VALUES (?, ?, ?)", (gid, qid, idx))

        new_conn.execute("INSERT INTO followup_nodes SELECT * FROM old.followup_nodes")

        # Read model_info from old
        cur = new_conn.execute("SELECT name, description, author, version, alto_version, created_at, updated_at FROM old.model_info")
        row = cur.fetchone()
        if row:
            name, desc, author, version, alto_ver, created, updated = row
        else:
            name, desc, author, version, alto_ver = self.name, "", "", "1.0.0", "0.1a"
            created = updated = now_iso
        new_conn.execute(
            "INSERT INTO model_info (name, description, author, version, alto_version, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, desc, author, version, alto_ver, created, updated)
        )

        new_conn.execute("DETACH old")
        new_conn.commit()
        new_conn.close()

        folder = find_model_dir(self.name)
        safe = safe_filename(self.name)
        container_path = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.rbm")
        fd, tmp_path = tempfile.mkstemp(suffix='.rbm', dir=os.path.dirname(container_path))
        os.close(fd)
        try:
            pack_model(new_db_path, get_model_info(sqlite3.connect(new_db_path)), tmp_path)
            os.replace(tmp_path, container_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        for ext in ['.db', '.db-wal', '.db-shm']:
            f = legacy_db_path.replace('.db', ext) if ext != '.db' else legacy_db_path
            if os.path.exists(f):
                os.remove(f)

    def close_and_repack(self):
        if self.conn is None:
            return
        manifest = get_model_info(self.conn)
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.close()
        self.conn = None
        fd, tmp_path = tempfile.mkstemp(suffix='.rbm', dir=os.path.dirname(self.container_path))
        os.close(fd)
        try:
            pack_model(self.db_path, manifest, tmp_path)
            os.replace(tmp_path, self.container_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def close_without_repack(self):
        if self.conn is None:
            return
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.close()
        self.conn = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _load_group_summaries(self):
        cur = self.conn.execute("""
            SELECT g.id, g.group_name,
                   COALESCE(t.name, '') as topic,
                   COALESCE(s.name, '') as section,
                   (SELECT GROUP_CONCAT(q.text, '|') FROM group_questions gq JOIN questions q ON gq.question_id = q.id WHERE gq.group_id = g.id ORDER BY gq.sort_order) as questions_text
            FROM groups g
            LEFT JOIN topics t ON g.topic_id = t.id
            LEFT JOIN sections s ON g.section_id = s.id
            ORDER BY g.id
        """)
        self._group_summaries = []
        for row in cur:
            self._group_summaries.append({
                "id": row[0],
                "group_name": row[1],
                "topic": row[2],
                "section": row[3],
                "questions": row[4].split('|') if row[4] else []
            })

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
                   g.answers_blob, g.created_at, g.updated_at
            FROM groups g
            WHERE g.id = ?
        """, (group_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Group id {group_id} not found")
        answers_blob = decompress_blob(row[4])
        answers = unpack_array(answers_blob)
        cur_q = self.conn.execute("""
            SELECT q.text FROM group_questions gq
            JOIN questions q ON gq.question_id = q.id
            WHERE gq.group_id = ?
            ORDER BY gq.sort_order
        """, (group_id,))
        questions = [r[0] for r in cur_q]
        group = {
            "id": row[0],
            "group_name": row[1],
            "topic": _get_topic_name(self.conn, row[2]),
            "section": _get_section_name(self.conn, row[3]),
            "questions": questions,
            "answers": answers,
            "created_at": row[5],
            "updated_at": row[6]
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
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            delete_group(self.conn, group_id)
            self.conn.commit()
            self._group_summaries = None
        except Exception:
            self.conn.rollback()
            raise

    # ---------- Section management (unchanged) ----------
    def add_section(self, name: str) -> int:
        self.last_used = time.time()
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute("SELECT id FROM sections WHERE name = ?", (name,))
            if cur.fetchone() is not None:
                raise ValueError(f"Section '{name}' already exists")
            cur = conn.execute("SELECT COALESCE(MAX(sort_order), -1) FROM sections")
            max_order = cur.fetchone()[0]
            cur = conn.execute(
                "INSERT INTO sections (name, sort_order) VALUES (?, ?) RETURNING id",
                (name, max_order + 1)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
        except Exception:
            conn.rollback()
            raise

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
        if action == "delete":
            cur = conn.execute("SELECT id FROM groups WHERE section_id = ?", (section_id,))
            group_ids = [row[0] for row in cur.fetchall()]
            for gid in group_ids:
                self.delete_group(gid)
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("UPDATE topics SET section_id = NULL WHERE section_id = ?", (section_id,))
                conn.execute("UPDATE variant_groups SET section_id = NULL WHERE section_id = ?", (section_id,))
                conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            return
        conn.execute("BEGIN IMMEDIATE")
        try:
            if action == "uncategorized":
                conn.execute("UPDATE groups SET section_id = NULL WHERE section_id = ?", (section_id,))
                conn.execute("UPDATE topics SET section_id = NULL WHERE section_id = ?", (section_id,))
                conn.execute("UPDATE variant_groups SET section_id = NULL WHERE section_id = ?", (section_id,))
            elif action == "move":
                if target_id is None:
                    raise ValueError("Target section required for move action")
                conn.execute("UPDATE groups SET section_id = ? WHERE section_id = ?", (target_id, section_id))
                conn.execute("UPDATE topics SET section_id = ? WHERE section_id = ?", (target_id, section_id))
                conn.execute("UPDATE variant_groups SET section_id = ? WHERE section_id = ?", (target_id, section_id))
            else:
                raise ValueError(f"Invalid action: {action}")
            conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ---------- Topic management (unchanged) ----------
    def add_topic(self, name: str, section_name: Optional[str] = None) -> int:
        self.last_used = time.time()
        section_id = _get_section_id(self.conn, section_name) if section_name else None
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute("SELECT id FROM topics WHERE name = ?", (name,))
            if cur.fetchone() is not None:
                raise ValueError(f"Topic '{name}' already exists")
            cur = conn.execute(
                "INSERT INTO topics (name, section_id) VALUES (?, ?) RETURNING id",
                (name, section_id)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
        except Exception:
            conn.rollback()
            raise

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
        if action == "delete_groups":
            cur = conn.execute("SELECT id FROM groups WHERE topic_id = ?", (topic_id,))
            group_ids = [row[0] for row in cur.fetchall()]
            for gid in group_ids:
                self.delete_group(gid)
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            return
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("UPDATE groups SET topic_id = ? WHERE topic_id = ?", (target_id, topic_id))
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

    # ---------- Variant management (unchanged) ----------
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
                conn.execute("INSERT INTO variant_words (word, group_id) VALUES (?, ?)", (word, group_id))
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
                conn.execute("INSERT INTO variant_words (word, group_id) VALUES (?, ?)", (word, variant_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def delete_variant(self, variant_id: int):
        self.last_used = time.time()
        self.conn.execute("DELETE FROM variant_groups WHERE id = ?", (variant_id,))
        self.conn.commit()

# ----------------------------------------------------------------------
# Global cache
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
            oldest_model.close_and_repack()
        _model_cache[name] = model
        return model

def close_all_models():
    for model in _model_cache.values():
        model.close_and_repack()
    _model_cache.clear()