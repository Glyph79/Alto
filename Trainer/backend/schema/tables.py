import sqlite3
import datetime
from typing import Dict, Any
from .constants import ALTO_VERSION, DEFAULT_TOPICS

def create_empty_schema(conn: sqlite3.Connection):
    """Create all tables without timestamps or sections."""
    conn.execute("""
        CREATE TABLE model_info (
            name TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            author TEXT NOT NULL,
            version TEXT NOT NULL,
            alto_version TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE topics (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE groups (
            id INTEGER PRIMARY KEY,
            group_name TEXT NOT NULL,
            topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
            fallback_id INTEGER REFERENCES fallbacks(id) ON DELETE SET NULL,
            questions_blob_id INTEGER NOT NULL DEFAULT 0,
            answers_blob_id INTEGER NOT NULL DEFAULT 0,
            answer_count INTEGER NOT NULL DEFAULT 0
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
            questions_blob_id INTEGER NOT NULL DEFAULT 0,
            answers_blob_id INTEGER NOT NULL DEFAULT 0,
            fallback_id INTEGER REFERENCES fallbacks(id) ON DELETE SET NULL
        )
    """)
    conn.execute("""
        CREATE TABLE variant_groups (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE variant_words (
            word TEXT NOT NULL,
            group_id INTEGER NOT NULL REFERENCES variant_groups(id) ON DELETE CASCADE,
            PRIMARY KEY (word, group_id)
        ) WITHOUT ROWID
    """)
    conn.execute("""
        CREATE TABLE fallbacks (
            id INTEGER PRIMARY KEY,
            name TEXT,
            description TEXT NOT NULL,
            answers_blob_id INTEGER NOT NULL DEFAULT 0,
            answer_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE blob_store (
            id INTEGER PRIMARY KEY,
            hash TEXT UNIQUE NOT NULL,
            data BLOB NOT NULL,
            ref_count INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Indexes
    conn.execute("CREATE INDEX idx_groups_topic ON groups(topic_id)")
    conn.execute("CREATE INDEX idx_groups_fallback ON groups(fallback_id)")
    conn.execute("CREATE INDEX idx_followup_nodes_group_parent ON followup_nodes(group_id, parent_id)")
    conn.execute("CREATE INDEX idx_followup_nodes_parent ON followup_nodes(parent_id)")
    conn.execute("CREATE INDEX idx_followup_nodes_fallback ON followup_nodes(fallback_id)")
    conn.execute("CREATE INDEX idx_group_questions_group ON group_questions(group_id)")
    conn.execute("CREATE INDEX idx_group_questions_question ON group_questions(question_id)")
    conn.execute("CREATE INDEX idx_fallbacks_id ON fallbacks(id)")
    conn.execute("CREATE INDEX idx_blob_store_hash ON blob_store(hash)")
    conn.execute("CREATE INDEX idx_variant_words_word ON variant_words(word)")

def init_model_db(conn: sqlite3.Connection, model_name: str, description: str, author: str, version: str):
    """Create full schema with default topics."""
    create_empty_schema(conn)

    for name in DEFAULT_TOPICS:
        conn.execute("INSERT INTO topics (name) VALUES (?)", (name,))

    conn.execute(
        """INSERT INTO model_info
           (name, description, author, version, alto_version)
           VALUES (?, ?, ?, ?, ?)""",
        (model_name, description, author, version, ALTO_VERSION)
    )
    conn.commit()

def get_model_info(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.execute("SELECT name, description, author, version, alto_version FROM model_info")
    row = cur.fetchone()
    if not row:
        raise ValueError("Model info not found")
    cur = conn.execute("SELECT name FROM topics ORDER BY name")
    topics = [r[0] for r in cur]
    return {
        "name": row[0],
        "description": row[1],
        "author": row[2],
        "version": row[3],
        "alto_version": row[4],
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
    conn.execute(
        """UPDATE model_info
           SET description = ?, author = ?, version = ?
           WHERE name = ?""",
        (info["description"], info["author"], info["version"], info["name"])
    )
    conn.commit()
    return info