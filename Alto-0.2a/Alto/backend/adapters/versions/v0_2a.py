# Alto/backend/adapters/versions/v0_2a.py
import os
import hashlib
import tarfile
import sqlite3
import msgpack
import re
import zstandard as zstd
from typing import List, Dict, Set
from ..base import BaseAdapter, CACHE_ROOT, get_model_container_path, \
                   FEATURE_CUSTOM_FALLBACKS, FEATURE_VARIANTS, FEATURE_FULL_TEXT_SEARCH, \
                   FEATURE_TOPICS, FEATURE_FOLLOWUP_TREES

class AdapterV0_2a(BaseAdapter):
    VERSION = "0.2a"

    def __init__(self):
        self._connections = {}
        self._current_model = None

    def get_version(self) -> str:
        return self.VERSION

    def get_connection(self, model_name: str) -> sqlite3.Connection:
        if model_name in self._connections:
            self._current_model = model_name
            return self._connections[model_name]

        container_path = get_model_container_path(model_name)
        if not container_path or not os.path.isfile(container_path):
            raise FileNotFoundError(f"Model '{model_name}' not found (.rbm container missing)")

        mtime = os.path.getmtime(container_path)
        key = hashlib.md5(f"{model_name}_{mtime}".encode()).hexdigest()[:16]
        cache_dir = os.path.join(CACHE_ROOT, model_name, key)
        db_path = os.path.join(cache_dir, "database.db")

        if not (os.path.isfile(db_path) and os.path.getmtime(db_path) >= mtime):
            os.makedirs(cache_dir, exist_ok=True)
            with tarfile.open(container_path, 'r') as tar:
                tar.extractall(cache_dir)
            if not os.path.isfile(db_path):
                raise RuntimeError(f"Extraction failed: {db_path} missing")

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        conn.execute("PRAGMA query_only = 1")
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

    def _decompress_blob(self, blob_id: int) -> bytes:
        if blob_id == 0:
            return b''
        conn = self._get_conn()
        cur = conn.execute("SELECT data FROM blob_store WHERE id = ?", (blob_id,))
        row = cur.fetchone()
        if not row:
            return b''
        compressed = row[0]
        if not compressed:
            return b''
        flag = compressed[0]
        payload = compressed[1:]
        if flag == 1:
            return zstd.decompress(payload)
        else:
            return payload

    def get_group_questions(self, group_id: int) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("""
            SELECT q.text FROM group_questions gq
            JOIN questions q ON gq.question_id = q.id
            WHERE gq.group_id = ?
            ORDER BY gq.sort_order
        """, (group_id,))
        return [row[0] for row in cur]

    def get_group_answers(self, group_id: int) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT answers_blob_id FROM groups WHERE id = ?", (group_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            return []
        blob_data = self._decompress_blob(row[0])
        return self._unpack(blob_data) if blob_data else []

    def get_group_data(self, group_id: int) -> Dict:
        conn = self._get_conn()
        cur = conn.execute("""
            SELECT g.id, g.group_name, COALESCE(t.name, '') as topic, g.fallback_id
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
            "questions": self.get_group_questions(group_id),
            "answers": self.get_group_answers(group_id),
            "fallback_id": row[3]
        }

    def get_root_nodes(self, group_id: int) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.execute("""
            SELECT id, branch_name, fallback_id
            FROM followup_nodes
            WHERE group_id = ? AND parent_id IS NULL
            ORDER BY id
        """, (group_id,))
        return [{"id": row[0], "branch_name": row[1], "fallback_id": row[2]} for row in cur]

    def get_node_children(self, node_id: int) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.execute("""
            SELECT id, branch_name, fallback_id
            FROM followup_nodes
            WHERE parent_id = ?
            ORDER BY id
        """, (node_id,))
        return [{"id": row[0], "branch_name": row[1], "fallback_id": row[2]} for row in cur]

    def get_node_questions(self, node_id: int) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT questions_blob_id FROM followup_nodes WHERE id = ?", (node_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            return []
        blob_data = self._decompress_blob(row[0])
        return self._unpack(blob_data) if blob_data else []

    def get_node_answers(self, node_id: int) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT answers_blob_id FROM followup_nodes WHERE id = ?", (node_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            return []
        blob_data = self._decompress_blob(row[0])
        return self._unpack(blob_data) if blob_data else []

    def get_topics(self) -> List[str]:
        conn = self._get_conn()
        cur = conn.execute("SELECT name FROM topics ORDER BY name")
        return [row[0] for row in cur]

    def get_sections(self) -> List[str]:
        try:
            conn = self._get_conn()
            cur = conn.execute("SELECT name FROM sections ORDER BY sort_order")
            return [row[0] for row in cur]
        except sqlite3.OperationalError:
            return []

    def get_variants(self) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.execute("""
            SELECT vg.id, vg.name,
                   GROUP_CONCAT(vw.word, ',') as words
            FROM variant_groups vg
            LEFT JOIN variant_words vw ON vw.group_id = vg.id
            GROUP BY vg.id
            ORDER BY vg.id
        """)
        variants = []
        for row in cur:
            words = row[2].split(',') if row[2] else []
            variants.append({"id": row[0], "name": row[1], "words": words})
        return variants

    def expand_synonyms(self, words: List[str]) -> Set[str]:
        if not words:
            return set()
        expanded = set()
        conn = self._get_conn()
        for w in words:
            cur = conn.execute(
                "SELECT DISTINCT v2.word FROM variant_words v1 "
                "JOIN variant_words v2 ON v1.group_id = v2.group_id WHERE v1.word = ?", (w,)
            )
            rows = cur.fetchall()
            if rows:
                expanded.update(r[0] for r in rows)
            else:
                expanded.add(w)
        return expanded

    def get_fallback_answers(self, fallback_id: int) -> List[str]:
        if not fallback_id:
            return []
        conn = self._get_conn()
        cur = conn.execute("SELECT answers_blob_id FROM fallbacks WHERE id = ?", (fallback_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            return []
        blob_data = self._decompress_blob(row[0])
        return self._unpack(blob_data) if blob_data else []

    def get_supported_features(self) -> dict:
        return {
            FEATURE_CUSTOM_FALLBACKS: True,
            FEATURE_VARIANTS: True,
            FEATURE_FULL_TEXT_SEARCH: True,
            FEATURE_TOPICS: True,
            FEATURE_FOLLOWUP_TREES: True,
        }