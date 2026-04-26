# alto/core/adapters/model.py
import re
import sqlite3
from rapidfuzz import fuzz, distance
from typing import Dict, List, Optional, Tuple, Set
from .base import get_adapter, FEATURE_CUSTOM_FALLBACKS
from ...config import config
from ..cache import SharedDataCache
from ..jit_cache import JITCache

DEBUG = config.getboolean('ai', 'debug', fallback=False)
RAM_ONLY_MODE = config.getboolean('ai', 'ram_only_mode', fallback=False)
ENABLE_JIT = config.getboolean('ai', 'enable_jit_cache', fallback=True)

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
        self.max_candidate_groups = config.getint('ai', 'max_candidate_groups', fallback=50)

        # RAM‑only mode: copy the entire database into an in‑memory connection
        self._ram_conn = None
        if RAM_ONLY_MODE:
            debug_print("🔧 RAM‑only mode enabled: copying database to memory...")
            source_conn = self.adapter._get_conn()
            self._ram_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._ram_conn.row_factory = sqlite3.Row
            source_conn.backup(self._ram_conn)
            debug_print("✅ Database copied to memory (FTS5 index preserved)")

        # JIT cache (server‑wide singleton)
        self.jit_cache = JITCache() if ENABLE_JIT else None

        # ---------- COMPACT VARIANT MAPPING (memory efficient) ----------
        self._word_to_group: Dict[str, int] = {}
        self._group_expansion: List[str] = []
        variants = self.adapter.get_variants()
        for vg in variants:
            gid = vg["id"]
            words = vg["words"]
            if not words:
                continue
            self._group_expansion.append(" ".join(words))
            for w in words:
                self._word_to_group[w] = gid
        debug_print(f"📘 Loaded {len(self._word_to_group)} variant words in {len(self._group_expansion)} groups (compact mapping)")

    def get_version(self) -> str:
        return self._version

    def supports_feature(self, feature: str) -> bool:
        features = self.adapter.get_supported_features()
        return features.get(feature, False)

    def _norm_word(self, w: str) -> str:
        return re.sub(r'[^\w\s]', '', w.lower())

    def _get_group_data(self, gid: int) -> Dict:
        def loader(group_id):
            return self.adapter.get_group_data(group_id)
        return self._cache.get_group(gid, loader)

    def get_node_data(self, node_id: int) -> Dict:
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
        if not self.supports_feature(FEATURE_CUSTOM_FALLBACKS):
            return []
        def loader(fid):
            return self.adapter.get_fallback_answers(fid)
        return self._cache.get_fallback(fallback_id, loader)

    # ---------- MEMORY‑EFFICIENT SYNONYM EXPANSION ----------
    def expand_synonyms(self, words: List[str]) -> Set[str]:
        expanded = set()
        for w in words:
            gid = self._word_to_group.get(w)
            if gid is not None:
                expanded.update(self._group_expansion[gid].split())
            else:
                expanded.add(w)
        return expanded

    @property
    def cache(self) -> SharedDataCache:
        return self._cache

    # ---------- DYNAMIC TYPO CORRECTION (JIT only, no static dictionary) ----------
    def correct_word(self, word: str) -> str:
        """Return corrected word using only JIT cache (no static dictionary)."""
        if not self.jit_cache:
            return word
        word_lower = word.lower()
        cached = self.jit_cache.get_typo(word_lower)
        if cached is not None:
            debug_print(f"🔁 Typo cache hit: '{word}' -> '{cached}'")
            return cached
        # No correction known yet; return original
        return word

    def correct_sentence(self, text: str) -> str:
        words = text.split()
        corrected_words = [self.correct_word(w) for w in words]
        return " ".join(corrected_words)

    def learn_typos_from_match(self, user_text: str, matched_question: str):
        """
        After a successful fuzzy match, compare user's original words
        with words in the matched question and store corrections.
        """
        if not self.jit_cache:
            return
        user_words = set(self._norm_word(w) for w in user_text.split())
        q_words = set(self._norm_word(w) for w in matched_question.split())
        for uw in user_words:
            if uw in q_words:
                continue
            best = None
            best_score = 0
            for qw in q_words:
                # Use rapidfuzz to find best matching word in the question
                score = fuzz.ratio(uw, qw)
                if score > best_score:
                    best_score = score
                    best = qw
            if best and best_score >= 85:
                self.jit_cache.set_typo(uw, best)
                debug_print(f"📝 Learned typo: '{uw}' -> '{best}' (score {best_score})")

    # ---------- Existing matching methods ----------
    def match_groups(self, text: str, topic_weights: Dict[str, int]) -> Tuple[Optional[int], Optional[Dict], int]:
        words = [self._norm_word(w) for w in text.split() if w]
        expanded = self.expand_synonyms(words)
        if not expanded:
            return None, None, 0

        if RAM_ONLY_MODE and self._ram_conn:
            conn = self._ram_conn
        else:
            conn = self.adapter._get_conn()

        match = ' OR '.join(f'"{w}"' for w in expanded)
        limit = self.max_candidate_groups

        try:
            cur = conn.execute(
                f"SELECT rowid FROM questions_fts WHERE questions_fts MATCH ? LIMIT ?",
                (match, limit * 10)
            )
            qids = [row[0] for row in cur]
        except sqlite3.OperationalError:
            cur = conn.execute(
                f"SELECT group_id FROM questions_fts WHERE questions_fts MATCH ? LIMIT ?",
                (match, limit * 10)
            )
            qids = [row[0] for row in cur]

        if not qids:
            return None, None, 0

        if self._version == "0.2a":
            placeholders = ','.join(['?'] * len(qids))
            cur = conn.execute(
                f"""
                SELECT DISTINCT group_id
                FROM group_questions
                WHERE question_id IN ({placeholders})
                ORDER BY group_id
                LIMIT ?
                """,
                qids + [limit]
            )
        else:
            placeholders = ','.join(['?'] * len(qids))
            cur = conn.execute(
                f"""
                SELECT DISTINCT group_id
                FROM groups
                WHERE id IN ({placeholders})
                ORDER BY id
                LIMIT ?
                """,
                qids + [limit]
            )
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