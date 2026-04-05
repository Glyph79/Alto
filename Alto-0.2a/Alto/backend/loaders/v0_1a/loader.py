import os
import hashlib
import sqlite3
import msgpack
import re
from fuzzywuzzy import fuzz
from typing import List, Dict, Optional, Tuple, Set
from ..base import BaseLoader, CACHE_ROOT, get_legacy_db_path

class LoaderV0_1a(BaseLoader):
    VERSION = "0.1a"

    def __init__(self):
        self._conn = None

    def get_version(self) -> str:
        return self.VERSION

    def get_connection(self, model_name: str) -> sqlite3.Connection:
        legacy_path = get_legacy_db_path(model_name)
        if not legacy_path or not os.path.isfile(legacy_path):
            raise FileNotFoundError(f"Model '{model_name}' not found (legacy .db missing)")

        mtime = os.path.getmtime(legacy_path)
        key = hashlib.md5(f"{model_name}_{mtime}".encode()).hexdigest()[:16]
        cache_dir = os.path.join(CACHE_ROOT, model_name, "v0_1a", key)
        os.makedirs(cache_dir, exist_ok=True)
        temp_db_path = os.path.join(cache_dir, "compat.db")

        if os.path.isfile(temp_db_path) and os.path.getmtime(temp_db_path) >= mtime:
            conn = sqlite3.connect(f"file:{temp_db_path}?mode=ro", uri=True, check_same_thread=False)
            conn.execute("PRAGMA query_only = 1")
            conn.row_factory = sqlite3.Row
            self._conn = conn
            return conn

        # Create view‑based compatibility database
        conn = sqlite3.connect(temp_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"ATTACH DATABASE '{legacy_path}' AS original")

        # Groups view with computed question_count and answer_count
        conn.execute("""
            CREATE VIEW groups AS
            SELECT
                g.id,
                g.group_name,
                g.topic_id,
                g.section_id,
                g.questions_blob,
                g.answers_blob,
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
        conn.row_factory = sqlite3.Row
        self._conn = conn
        return conn

    def _unpack(self, data: bytes) -> list:
        return msgpack.unpackb(data, raw=False)

    def _norm_word(self, w: str) -> str:
        return re.sub(r'[^\w\s]', '', w.lower())

    def get_group_questions(self, group_id: int) -> List[str]:
        cur = self._conn.execute("SELECT questions_blob FROM groups WHERE id = ?", (group_id,))
        row = cur.fetchone()
        return self._unpack(row[0]) if row else []

    def get_group_answers(self, group_id: int) -> List[str]:
        cur = self._conn.execute("SELECT answers_blob FROM groups WHERE id = ?", (group_id,))
        row = cur.fetchone()
        return self._unpack(row[0]) if row else []

    def get_group_data(self, group_id: int) -> Dict:
        cur = self._conn.execute("""
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

    def match_groups(self, text: str, topic_weights: Dict[str, int], threshold: int) -> Tuple[Optional[int], Optional[Dict], int]:
        words = [self._norm_word(w) for w in text.split() if w]
        expanded = self.expand_synonyms(words)
        if not expanded:
            return None, None, 0

        match = ' OR '.join(f'"{w}"' for w in expanded)
        cur = self._conn.execute(
            "SELECT DISTINCT group_id FROM questions_fts WHERE questions_fts MATCH ?", (match,)
        )
        gids = [row[0] for row in cur]
        if not gids:
            return None, None, 0

        placeholders = ','.join(['?'] * len(gids))
        cur = self._conn.execute(f"""
            SELECT g.id, g.group_name, COALESCE(t.name, '') as topic
            FROM groups g
            LEFT JOIN topics t ON g.topic_id = t.id
            WHERE g.id IN ({placeholders})
        """, gids)
        groups = [dict(row) for row in cur]

        best_score = 0
        best_group = None
        text_low = text.lower()
        for grp in groups:
            questions = self.get_group_questions(grp["id"])
            base_score = 0
            for q in questions:
                score = fuzz.token_set_ratio(text_low, q.lower())
                if score > base_score:
                    base_score = score
            boost = topic_weights.get(grp["topic"], 0)
            final_score = base_score + boost
            if final_score > best_score:
                best_score = final_score
                best_group = grp
        if best_score >= threshold:
            full_group = self.get_group_data(best_group["id"])
            return best_group["id"], full_group, best_score
        return None, None, 0

    def get_root_nodes(self, group_id: int) -> List[Dict]:
        cur = self._conn.execute("""
            SELECT id, branch_name, questions_blob, answers_blob
            FROM followup_nodes
            WHERE group_id = ? AND parent_id IS NULL
            ORDER BY id
        """, (group_id,))
        nodes = []
        for row in cur:
            nodes.append({
                "id": row[0],
                "branch_name": row[1],
                "questions": self._unpack(row[2]),
                "answers": self._unpack(row[3]),
                "children": []
            })
        return nodes

    def get_node_children(self, node_id: int) -> List[Dict]:
        cur = self._conn.execute("""
            SELECT id, branch_name, questions_blob, answers_blob
            FROM followup_nodes
            WHERE parent_id = ?
            ORDER BY id
        """, (node_id,))
        children = []
        for row in cur:
            children.append({
                "id": row[0],
                "branch_name": row[1],
                "questions": self._unpack(row[2]),
                "answers": self._unpack(row[3]),
                "children": []
            })
        return children

    def get_node_questions(self, node_id: int) -> List[str]:
        cur = self._conn.execute("SELECT questions_blob FROM followup_nodes WHERE id = ?", (node_id,))
        row = cur.fetchone()
        return self._unpack(row[0]) if row else []

    def get_node_answers(self, node_id: int) -> List[str]:
        cur = self._conn.execute("SELECT answers_blob FROM followup_nodes WHERE id = ?", (node_id,))
        row = cur.fetchone()
        return self._unpack(row[0]) if row else []

    def match_nodes(self, text: str, nodes: List[Dict], threshold: int) -> Tuple[Optional[Dict], int]:
        best_score = 0
        best_node = None
        text_low = text.lower()
        for node in nodes:
            for q in node.get("questions", []):
                score = fuzz.token_set_ratio(text_low, q.lower())
                if score > best_score:
                    best_score = score
                    best_node = node
        if best_score >= threshold:
            return best_node, best_score
        return None, 0

    def get_topics(self) -> List[str]:
        cur = self._conn.execute("SELECT name FROM topics ORDER BY name")
        return [row[0] for row in cur]

    def get_sections(self) -> List[str]:
        cur = self._conn.execute("SELECT name FROM sections ORDER BY sort_order")
        return [row[0] for row in cur]

    def get_variants(self) -> List[Dict]:
        # 0.1a has no variants, return empty list
        return []

    def expand_synonyms(self, words: List[str]) -> set:
        # 0.1a has no variant words, return original words
        return set(words)