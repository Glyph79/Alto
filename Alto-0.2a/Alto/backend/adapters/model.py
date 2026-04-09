# Alto/backend/adapters/model.py – pure matcher
import re
from collections import OrderedDict
from rapidfuzz import fuzz
from typing import Dict, List, Optional, Tuple
from .base import BaseAdapter, get_adapter
from ..config import config

DEBUG = config.getboolean('ai', 'debug', fallback=False)

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

class Model:
    def __init__(self, model_name: str, threshold: int = None):
        self.model_name = model_name
        self.threshold = threshold if threshold is not None else config.getint('ai', 'threshold')
        self.fallback = config.get('DEFAULT', 'fallback')
        self.adapter = get_adapter(model_name)
        self.adapter.get_connection(model_name)
        debug_print(f"🤖 Initialized matcher for '{model_name}', version {self.adapter.get_version()}")
        self._group_cache = OrderedDict()
        self.GROUP_CACHE_SIZE = 3

    def _norm_word(self, w: str) -> str:
        return re.sub(r'[^\w\s]', '', w.lower())

    def _get_group_data(self, gid):
        if gid in self._group_cache:
            self._group_cache.move_to_end(gid)
            return self._group_cache[gid]
        data = self.adapter.get_group_data(gid)
        self._group_cache[gid] = data
        self._group_cache.move_to_end(gid)
        if len(self._group_cache) > self.GROUP_CACHE_SIZE:
            self._group_cache.popitem(last=False)
        return data

    def match_groups(self, text: str, topic_weights: Dict[str, int]) -> Tuple[Optional[int], Optional[Dict], int]:
        import sqlite3
        words = [self._norm_word(w) for w in text.split() if w]
        expanded = self.adapter.expand_synonyms(words)
        if not expanded:
            return None, None, 0

        conn = self.adapter._get_conn()
        match = ' OR '.join(f'"{w}"' for w in expanded)

        try:
            cur = conn.execute("SELECT rowid FROM questions_fts WHERE questions_fts MATCH ?", (match,))
            qids = [row[0] for row in cur]
        except sqlite3.OperationalError:
            cur = conn.execute("SELECT group_id FROM questions_fts WHERE questions_fts MATCH ?", (match,))
            qids = [row[0] for row in cur]

        if not qids:
            return None, None, 0

        if self.adapter.get_version() == "0.2a":
            placeholders = ','.join(['?'] * len(qids))
            cur = conn.execute(f"SELECT DISTINCT group_id FROM group_questions WHERE question_id IN ({placeholders})", qids)
        else:
            placeholders = ','.join(['?'] * len(qids))
            cur = conn.execute(f"SELECT DISTINCT group_id FROM groups WHERE id IN ({placeholders})", qids)
        gids = [row[0] for row in cur]
        if not gids:
            return None, None, 0

        placeholders2 = ','.join(['?'] * len(gids))
        cur = conn.execute(f"""
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
            questions = self.adapter.get_group_questions(grp["id"])
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

        if best_score >= self.threshold:
            full_group = self._get_group_data(best_group["id"])
            return best_group["id"], full_group, best_score
        return None, None, 0

    def match_nodes(self, text: str, nodes: List[Dict]) -> Tuple[Optional[Dict], int]:
        best_score = 0
        best_node = None
        text_low = text.lower()
        for node in nodes:
            for q in node.get("questions", []):
                score = fuzz.token_set_ratio(text_low, q.lower())
                if score > best_score:
                    best_score = score
                    best_node = node
        if best_score >= self.threshold:
            return best_node, best_score
        return None, 0