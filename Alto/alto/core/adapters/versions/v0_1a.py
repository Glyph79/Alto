# alto/core/adapters/versions/v0_1a.py
import os
import hashlib
import sqlite3
import msgpack
import re
from typing import List, Dict, Set
from ..base import BaseAdapter, CACHE_ROOT, get_legacy_db_path, \
                   FEATURE_FULL_TEXT_SEARCH, FEATURE_TOPICS, FEATURE_FOLLOWUP_TREES, FEATURE_SECTIONS

class AdapterV0_1a(BaseAdapter):
    VERSION = "0.1a"

    def __init__(self):
        self._connections = {}
        self._current_model = None

    def get_version(self) -> str:
        return self.VERSION

    def get_connection(self, model_name: str) -> sqlite3.Connection:
        if model_name in self._connections:
            self._current_model = model_name
            return self._connections[model_name]

        legacy_path = get_legacy_db_path(model_name)
        if not legacy_path or not os.path.isfile(legacy_path):
            raise FileNotFoundError(f"Model '{model_name}' not found (legacy .db missing)")

        mtime = os.path.getmtime(legacy_path)
        key = hashlib.md5(f"{model_name}_{mtime}".encode()).hexdigest()[:16]
        cache_dir = os.path.join(CACHE_ROOT, model_name, "v0_1a", key)
        os.makedirs(cache_dir, exist_ok=True)
        temp_db_path = os.path.join(cache_dir, "compat.db")

        if not (os.path.isfile(temp_db_path) and os.path.getmtime(temp_db_path) >= mtime):
            conn = sqlite3.connect(temp_db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(f"ATTACH DATABASE '{legacy_path}' AS original")

            conn.execute("""
                CREATE VIEW groups AS
                SELECT
                    g.id, g.group_name, g.topic_id, g.section_id,
                    g.questions_blob, g.answers_blob,
                    (SELECT COUNT(*) FROM original.questions_fts WHERE group_id = g.id) AS question_count,
                    (SELECT json_array_length(g.answers_blob)) AS answer_count
                FROM original.groups g
            """)
            conn.execute("CREATE VIEW sections AS SELECT * FROM original.sections")
            conn.execute("CREATE VIEW topics AS SELECT * FROM original.topics")
            conn.execute("CREATE VIEW variant_groups AS SELECT id, name, section_id, created_at FROM original.variant_groups WHERE 0")
            conn.execute("CREATE VIEW variant_words AS SELECT word, group_id FROM original.variant_words WHERE 0")
            conn.execute("CREATE VIEW followup_nodes AS SELECT * FROM original.followup_nodes")
            conn.execute("CREATE VIEW questions_fts AS SELECT group_id, question FROM original.questions_fts")
            conn.commit()
            conn.close()

        conn = sqlite3.connect(f"file:{temp_db_path}?mode=ro", uri=True, check_same_thread=False)
        conn.execute("PRAGMA query_only = 1")

        # ----- Optimizations for disk‑based model (conservative) -----
        conn.execute("PRAGMA cache_size = 5000")          # ~20 MB (4KB pages)
        conn.execute("PRAGMA mmap_size = 67108864")       # 64 MB memory mapping
        conn.execute("PRAGMA synchronous = NORMAL")       # reduce fsync (read-only, safe)
        conn.execute("PRAGMA temp_store = MEMORY")        # temp tables in RAM
        conn.execute("PRAGMA journal_mode = WAL")         # write-ahead logging

        conn.row_factory = sqlite3.Row
        self._connections[model_name] = conn
        self._current_model = model_name
        return conn

    def _get_conn(self, model_name: str = None) -> sqlite3.Connection:
        if model_name is None:
            model_name = self._current_model
        if model_name is None or model_name not in self._connections:
            raise RuntimeError("No active model connection. Call get_connection() first.")
        return self._connections[model_name]

    def _unpack(self, data: bytes) -> list:
        return msgpack.unpackb(data, raw=False)

    def get_group_questions(self, group_id: int) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT questions_blob FROM groups WHERE id = ?", (group_id,))
        row = cur.fetchone()
        return self._unpack(row[0]) if row else []

    def get_group_answers(self, group_id: int) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT answers_blob FROM groups WHERE id = ?", (group_id,))
        row = cur.fetchone()
        return self._unpack(row[0]) if row else []

    def get_group_data(self, group_id: int) -> Dict:
        conn = self._get_conn()
        cur = conn.execute("""
            SELECT g.id, g.group_name, COALESCE(t.name, '') as topic,
                   g.questions_blob, g.answers_blob
            FROM groups g
            LEFT JOIN topics t ON g.topic_id = t.id
            WHERE g.id = ?
        """, (group_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Group {group_id} not found")
        return {
            "id": row[0],
            "group_name": row[1],
            "topic": row[2],
            "questions": self._unpack(row[3]),
            "answers": self._unpack(row[4]),
            "created_at": None,
            "updated_at": None
        }

    def get_root_nodes(self, group_id: int) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.execute("""
            SELECT id, branch_name
            FROM followup_nodes
            WHERE group_id = ? AND parent_id IS NULL
            ORDER BY id
        """, (group_id,))
        return [{"id": row[0], "branch_name": row[1]} for row in cur]

    def get_node_children(self, node_id: int) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.execute("""
            SELECT id, branch_name
            FROM followup_nodes
            WHERE parent_id = ?
            ORDER BY id
        """, (node_id,))
        return [{"id": row[0], "branch_name": row[1]} for row in cur]

    def get_node_questions(self, node_id: int) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT questions_blob FROM followup_nodes WHERE id = ?", (node_id,))
        row = cur.fetchone()
        return self._unpack(row[0]) if row else []

    def get_node_answers(self, node_id: int) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT answers_blob FROM followup_nodes WHERE id = ?", (node_id,))
        row = cur.fetchone()
        return self._unpack(row[0]) if row else []

    def get_topics(self) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT name FROM topics ORDER BY name")
        return [row[0] for row in cur]

    def get_sections(self) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT name FROM sections ORDER BY sort_order")
        return [row[0] for row in cur]

    def get_variants(self) -> List[Dict]:
        return []

    def expand_synonyms(self, words: List[str]) -> Set[str]:
        return set(words)

    def get_supported_features(self) -> dict:
        return {
            FEATURE_FULL_TEXT_SEARCH: True,
            FEATURE_TOPICS: True,
            FEATURE_FOLLOWUP_TREES: True,
            FEATURE_SECTIONS: True,
        }