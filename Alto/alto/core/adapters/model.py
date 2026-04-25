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
            self._ram_conn.row_factory = sqlite3.Row   # <-- FIX: set row factory
            source_conn.backup(self._ram_conn)
            debug_print("✅ Database copied to memory (FTS5 index preserved)")

        # JIT cache (server‑wide singleton)
        self.jit_cache = JITCache() if ENABLE_JIT else None
        # Known words for typo correction (lazy loaded)
        self._known_words = None

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

    def expand_synonyms(self, words: List[str]) -> Set[str]:
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

    # ---------- JIT cache: typo correction ----------
    def _build_known_words(self):
        """Build a set of all known words from variant groups and question texts."""
        if self._known_words is not None:
            return
        known = set()
        # Add words from variant groups
        variants = self.adapter.get_variants()
        for vg in variants:
            for w in vg.get('words', []):
                known.add(w.lower())
        # Add unique words from questions table (via FTS or direct query)
        try:
            conn = self.adapter._get_conn()
            # Get all unique words from questions (simplified: split and collect)
            cur = conn.execute("SELECT text FROM questions")
            for row in cur:
                for w in row[0].lower().split():
                    known.add(re.sub(r'[^\w]', '', w))
        except Exception as e:
            debug_print(f"⚠️ Could not build known words from questions: {e}")
        self._known_words = known
        debug_print(f"📚 Built known words set with {len(known)} entries")

    def correct_word(self, word: str) -> str:
        """Return corrected word using JIT cache and Levenshtein distance."""
        if not self.jit_cache:
            return word
        word_lower = word.lower()
        # Check cache first
        cached = self.jit_cache.get_typo(word_lower)
        if cached is not None:
            debug_print(f"🔁 Typo cache hit: '{word}' -> '{cached}'")
            return cached
        # Ensure known words are loaded
        if self._known_words is None:
            self._build_known_words()
        # Find best correction among known words
        best_match = word_lower
        best_dist = 2  # Max edit distance allowed
        for known in self._known_words:
            dist = distance.Levenshtein.distance(word_lower, known)
            if dist < best_dist:
                best_dist = dist
                best_match = known
        # Only store if correction actually changed the word
        if best_match != word_lower:
            debug_print(f"🔧 New typo learned: '{word}' -> '{best_match}' (dist={best_dist})")
            self.jit_cache.set_typo(word_lower, best_match)
            return best_match
        # No correction found, store identity to avoid recomputation
        self.jit_cache.set_typo(word_lower, word_lower)
        return word_lower

    def correct_sentence(self, text: str) -> str:
        """Apply word‑level correction to whole sentence."""
        words = text.split()
        corrected_words = [self.correct_word(w) for w in words]
        return " ".join(corrected_words)

    # ---------- Existing matching methods ----------
    def match_groups(self, text: str, topic_weights: Dict[str, int]) -> Tuple[Optional[int], Optional[Dict], int]:
        words = [self._norm_word(w) for w in text.split() if w]
        expanded = self.expand_synonyms(words)
        if not expanded:
            return None, None, 0

        # Use in‑memory connection if RAM‑only mode is enabled, otherwise the adapter's connection
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