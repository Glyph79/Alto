# alto/core/adapters/model.py
import re
from collections import OrderedDict
from rapidfuzz import fuzz
from typing import Dict, List, Optional, Tuple, Set
from .base import get_adapter, FEATURE_CUSTOM_FALLBACKS
from ...config import config
from ..cache import SharedDataCache

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
        self._version = self.adapter.get_version()
        debug_print(f"🤖 Initialized matcher for '{model_name}', version {self._version}")
        self._cache = SharedDataCache()

    def get_version(self) -> str:
        return self._version

    def supports_feature(self, feature: str) -> bool:
        features = self.adapter.get_supported_features()
        return features.get(feature, False)

    def _norm_word(self, w: str) -> str:
        return re.sub(r'[^\w\s]', '', w.lower())

    def _get_group_data(self, gid: int) -> Dict:
        """Fetch group data from shared cache."""
        def loader(group_id):
            return self.adapter.get_group_data(group_id)
        return self._cache.get_group(gid, loader)

    def get_node_data(self, node_id: int) -> Dict:
        """Fetch complete node data (questions, answers, children, etc.) from cache."""
        def loader(nid):
            children = self.adapter.get_node_children(nid)
            node = {
                'id': nid,
                'branch_name': '',
                'questions': self.adapter.get_node_questions(nid),
                'answers': self.adapter.get_node_answers(nid),
                'fallback_id': None,
                'children': children,
                'children_ids': [c['id'] for c in children]
            }
            return node
        return self._cache.get_node(node_id, loader)

    def get_fallback_answers(self, fallback_id: int) -> List[str]:
        """Fetch fallback answers from shared cache."""
        if not self.supports_feature(FEATURE_CUSTOM_FALLBACKS):
            return []
        def loader(fid):
            return self.adapter.get_fallback_answers(fid)
        return self._cache.get_fallback(fallback_id, loader)

    def expand_synonyms(self, words: List[str]) -> Set[str]:
        """Use cached variant map."""
        def loader():
            variants = self.adapter.get_variants()
            mapping = {}
            for vg in variants:
                words_set = set(vg['words'])
                for w in words_set:
                    mapping[w] = words_set
            return mapping
        variants_map = self._cache.get_variants_map(loader)
        expanded = set()
        for w in words:
            if w in variants_map:
                expanded.update(variants_map[w])
            else:
                expanded.add(w)
        return expanded

    @property
    def cache(self) -> SharedDataCache:
        return self._cache

    def match_groups(self, text: str, topic_weights: Dict[str, int]) -> Tuple[Optional[int], Optional[Dict], int]:
        import sqlite3
        words = [self._norm_word(w) for w in text.split() if w]
        expanded = self.expand_synonyms(words)
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

        if self._version == "0.2a":
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