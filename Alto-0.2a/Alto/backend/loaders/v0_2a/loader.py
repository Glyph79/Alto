import os
import hashlib
import tarfile
import sqlite3
import msgpack
import re
import zlib
from fuzzywuzzy import fuzz
from typing import List, Dict, Optional, Tuple, Set
from ..base import BaseLoader, CACHE_ROOT, get_model_container_path

class LoaderV0_2a(BaseLoader):
    VERSION = "0.2a"

    def __init__(self):
        self._conn = None

    def get_version(self) -> str:
        return self.VERSION

    def get_connection(self, model_name: str) -> sqlite3.Connection:
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
        self._conn = conn
        return conn

    def _unpack(self, data: bytes) -> list:
        return msgpack.unpackb(data, raw=False)

    def _norm_word(self, w: str) -> str:
        return re.sub(r'[^\w\s]', '', w.lower())

    # Unified skeleton methods
    def get_root_nodes(self, group_id: int) -> List[Dict]:
        cur = self._conn.execute("""
            SELECT id, branch_name
            FROM followup_nodes
            WHERE group_id = ? AND parent_id IS NULL
            ORDER BY id
        """, (group_id,))
        nodes = []
        for row in cur:
            nodes.append({
                "id": row[0],
                "branch_name": row[1],
                "questions": None,
                "answers": None
            })
        return nodes

    def get_node_children(self, node_id: int) -> List[Dict]:
        cur = self._conn.execute("""
            SELECT id, branch_name
            FROM followup_nodes
            WHERE parent_id = ?
            ORDER BY id
        """, (node_id,))
        children = []
        for row in cur:
            children.append({
                "id": row[0],
                "branch_name": row[1],
                "questions": None,
                "answers": None
            })
        return children

    # Full data (on demand)
    def get_node_questions(self, node_id: int) -> List[str]:
        cur = self._conn.execute("SELECT questions_blob FROM followup_nodes WHERE id = ?", (node_id,))
        row = cur.fetchone()
        if not row:
            return []
        return self._unpack(row[0])

    def get_node_answers(self, node_id: int) -> List[str]:
        cur = self._conn.execute("SELECT answers_blob FROM followup_nodes WHERE id = ?", (node_id,))
        row = cur.fetchone()
        if not row:
            return []
        return self._unpack(row[0])

    # Group methods
    def get_group_questions(self, group_id: int) -> List[str]:
        cur = self._conn.execute("""
            SELECT q.text FROM group_questions gq
            JOIN questions q ON gq.question_id = q.id
            WHERE gq.group_id = ?
            ORDER BY gq.sort_order
        """, (group_id,))
        return [row[0] for row in cur]

    def get_group_answers(self, group_id: int) -> List[str]:
        cur = self._conn.execute("SELECT answers_blob FROM groups WHERE id = ?", (group_id,))
        row = cur.fetchone()
        if not row:
            return []
        decompressed = zlib.decompress(row[0])
        return msgpack.unpackb(decompressed, raw=False)

    def get_group_data(self, group_id: int) -> Dict:
        cur = self._conn.execute("""
            SELECT g.id, g.group_name, COALESCE(t.name, '') as topic,
                   g.created_at, g.updated_at
            FROM groups g
            LEFT JOIN topics t ON g.topic_id = t.id
            WHERE g.id = ?
        """, (group_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Group {group_id} not found")
        answers = self.get_group_answers(group_id)
        questions = self.get_group_questions(group_id)
        return {
            "id": row[0],
            "group_name": row[1],
            "topic": row[2],
            "questions": questions,
            "answers": answers,
            "created_at": row[3],
            "updated_at": row[4]
        }

    def match_groups(self, text: str, topic_weights: Dict[str, int], threshold: int) -> Tuple[Optional[int], Optional[Dict], int]:
        words = [self._norm_word(w) for w in text.split() if w]
        expanded = self.expand_synonyms(words)
        if not expanded:
            return None, None, 0

        match = ' OR '.join(f'"{w}"' for w in expanded)
        cur = self._conn.execute(
            "SELECT rowid FROM questions_fts WHERE questions_fts MATCH ?", (match,)
        )
        qids = [row[0] for row in cur]
        if not qids:
            return None, None, 0

        placeholders = ','.join(['?'] * len(qids))
        cur = self._conn.execute(f"""
            SELECT DISTINCT group_id FROM group_questions
            WHERE question_id IN ({placeholders})
        """, qids)
        gids = [row[0] for row in cur]
        if not gids:
            return None, None, 0

        placeholders2 = ','.join(['?'] * len(gids))
        cur = self._conn.execute(f"""
            SELECT g.id, g.group_name, COALESCE(t.name, '') as topic
            FROM groups g
            LEFT JOIN topics t ON g.topic_id = t.id
            WHERE g.id IN ({placeholders2})
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
        cur = self._conn.execute("""
            SELECT vg.id, vg.name, COALESCE(s.name, '') as section,
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
            variants.append({"id": row[0], "name": row[1], "section": row[2], "words": words})
        return variants

    def expand_synonyms(self, words: List[str]) -> set:
        if not words:
            return set()
        expanded = set()
        for w in words:
            cur = self._conn.execute(
                "SELECT DISTINCT v2.word FROM variant_words v1 "
                "JOIN variant_words v2 ON v1.group_id = v2.group_id WHERE v1.word = ?", (w,)
            )
            rows = cur.fetchall()
            if rows:
                expanded.update(r[0] for r in rows)
            else:
                expanded.add(w)
        return expanded