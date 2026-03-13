import os
import re
import sqlite3
import msgpack
import random
from fuzzywuzzy import fuzz
from collections import OrderedDict

MODELS_BASE_DIR = os.path.join(os.path.dirname(__file__), "models")

def _safe_filename(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)

def _find_model_dir(model_name: str) -> str | None:
    safe = _safe_filename(model_name)
    if not os.path.exists(MODELS_BASE_DIR):
        return None
    for entry in os.listdir(MODELS_BASE_DIR):
        full_path = os.path.join(MODELS_BASE_DIR, entry)
        if not os.path.isdir(full_path):
            continue
        if entry.endswith('_' + safe):
            return entry
    return None

def _get_model_db_path(model_name: str) -> str | None:
    folder = _find_model_dir(model_name)
    if not folder:
        return None
    return os.path.join(MODELS_BASE_DIR, folder, "model.db")

def _unpack_array(data: bytes) -> list:
    return msgpack.unpackb(data, raw=False)

def _group_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row[0],
        "group_name": row[1],
        "topic": row[2],
        "priority": row[3],
        "section": row[4],
        "questions": _unpack_array(row[5]),
        "answers": _unpack_array(row[6]),
    }

def _normalize_word(word: str) -> str:
    return re.sub(r'[^\w\s]', '', word.lower())

def _get_group_ids_for_words(conn: sqlite3.Connection, words: list[str]) -> set[int]:
    """Return set of group IDs whose questions contain any of the given words (using FTS5)."""
    if not words:
        return set()
    # Build a MATCH expression: word1 OR word2 OR ...
    match_expr = ' OR '.join(f'"{w}"' for w in words)
    cur = conn.execute(
        "SELECT DISTINCT group_id FROM questions_fts WHERE questions_fts MATCH ?",
        (match_expr,)
    )
    return {row[0] for row in cur}

def _get_groups_by_ids(conn: sqlite3.Connection, group_ids: list[int]) -> list[dict]:
    """Load full group data for the given IDs."""
    if not group_ids:
        return []
    placeholders = ','.join(['?'] * len(group_ids))
    query = f"""
        SELECT id, group_name, topic, priority, section,
               questions_blob, answers_blob
        FROM groups
        WHERE id IN ({placeholders})
    """
    cur = conn.execute(query, group_ids)
    return [_group_from_row(row) for row in cur]

class RuleBot:
    DEFAULT_MODEL = "Alto"
    MAX_TREES = 3
    INACTIVITY_TIMEOUT = 10
    ENDED_TIMEOUT = 5
    DEFAULT_CACHE_TURNS = 5
    DEFAULT_MAX_CACHED_GROUPS = 3

    def __init__(self, model_name: str | None = None, threshold: int = 70,
                 group_cache_turns: int = DEFAULT_CACHE_TURNS,
                 max_cached_groups: int = DEFAULT_MAX_CACHED_GROUPS):
        """
        :param model_name: Name of the model to load.
        :param threshold: Minimum fuzzy match score to consider a match.
        :param group_cache_turns: Number of turns a group stays in cache without use before being evicted.
        :param max_cached_groups: Maximum number of groups to keep in the LRU cache.
        """
        self.threshold = threshold
        self.fallback = "I'm sorry, I didn't understand that."
        self.group_cache_turns = group_cache_turns
        self.max_cached_groups = max_cached_groups

        model = model_name or self.DEFAULT_MODEL
        db_path = _get_model_db_path(model)
        if not db_path or not os.path.isfile(db_path):
            raise FileNotFoundError(f"Model '{model}' not found or database missing")

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.row_factory = sqlite3.Row

        # LRU cache: group_id -> (group_data, last_used_turn)
        self._group_cache = OrderedDict()
        # Follow‑up tree cache (cleared when group evicted)
        self._followup_cache = {}

        self.turn = 0

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __del__(self):
        self.close()

    # ---------- Group loading with turn‑based LRU cache ----------
    def _load_group(self, group_id: int) -> dict:
        """
        Load a group, using cache if fresh. If the group is not in cache or has expired,
        load from database, add to cache, and enforce max cache size.
        """
        # Check cache
        if group_id in self._group_cache:
            group_data, last_turn = self._group_cache[group_id]
            if self.turn - last_turn < self.group_cache_turns:
                # Fresh – move to end (most recent) and return
                self._group_cache.move_to_end(group_id)
                self._group_cache[group_id] = (group_data, self.turn)
                return group_data
            else:
                # Expired – remove from caches
                del self._group_cache[group_id]
                self._followup_cache.pop(group_id, None)

        # Load from database
        cur = self.conn.execute(
            "SELECT id, group_name, topic, priority, section, "
            "questions_blob, answers_blob FROM groups WHERE id = ?",
            (group_id,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Group id {group_id} not found")
        group_data = _group_from_row(row)

        # Insert into cache, respecting max size
        self._group_cache[group_id] = (group_data, self.turn)
        self._group_cache.move_to_end(group_id)
        if len(self._group_cache) > self.max_cached_groups:
            # Remove least recently used (first item)
            oldest_id, _ = self._group_cache.popitem(last=False)
            self._followup_cache.pop(oldest_id, None)

        return group_data

    def _load_groups(self, group_ids: list[int]) -> list[dict]:
        """
        Load multiple groups, using cache where possible.
        Returns groups in the same order as group_ids (but cached ones may come first).
        """
        if not group_ids:
            return []

        result = []
        uncached_ids = []

        for gid in group_ids:
            if gid in self._group_cache:
                group_data, last_turn = self._group_cache[gid]
                if self.turn - last_turn < self.group_cache_turns:
                    # Fresh – use and update
                    self._group_cache.move_to_end(gid)
                    self._group_cache[gid] = (group_data, self.turn)
                    result.append(group_data)
                else:
                    # Expired – remove and queue for reload
                    del self._group_cache[gid]
                    self._followup_cache.pop(gid, None)
                    uncached_ids.append(gid)
            else:
                uncached_ids.append(gid)

        if uncached_ids:
            fresh_groups = _get_groups_by_ids(self.conn, uncached_ids)
            for g in fresh_groups:
                gid = g["id"]
                self._group_cache[gid] = (g, self.turn)
                self._group_cache.move_to_end(gid)
                result.append(g)

        # Enforce max size after batch additions
        while len(self._group_cache) > self.max_cached_groups:
            oldest_id, _ = self._group_cache.popitem(last=False)
            self._followup_cache.pop(oldest_id, None)

        return result

    # ---------- Matching (unchanged) ----------
    def _best_match_in_nodes(self, user_input: str, nodes: list[dict]) -> tuple[int | None, dict | None]:
        best_score = 0
        best_node = None
        user_lower = user_input.lower()
        for node in nodes:
            for q in node["questions"]:
                q_lower = q.lower()
                score = fuzz.token_set_ratio(user_lower, q_lower)
                if score > best_score:
                    best_score = score
                    best_node = node
        if best_score >= self.threshold:
            return best_score, best_node
        return None, None

    def _best_match_in_groups(self, user_input: str, groups: list[dict]) -> tuple[int | None, dict | None]:
        best_score = 0
        best_group = None
        user_lower = user_input.lower()
        for group in groups:
            for q in group["questions"]:
                q_lower = q.lower()
                score = fuzz.token_set_ratio(user_lower, q_lower)
                if score > best_score:
                    best_score = score
                    best_group = group
        if best_score >= self.threshold:
            return best_score, best_group
        return None, None

    def _random_answer(self, group: dict) -> str:
        if group and group.get("answers"):
            return random.choice(group["answers"])
        return self.fallback

    def _random_answer_from_node(self, node: dict) -> str:
        if node and node.get("answers"):
            return random.choice(node["answers"])
        return self.fallback

    def _get_follow_up_nodes(self, group_id: int) -> list[dict]:
        if group_id not in self._followup_cache:
            cur = self.conn.execute("SELECT follow_ups_blob FROM groups WHERE id = ?", (group_id,))
            row = cur.fetchone()
            if row and row[0]:
                nodes = _unpack_array(row[0])
                self._followup_cache[group_id] = nodes
            else:
                self._followup_cache[group_id] = []
        return self._followup_cache[group_id]

    def _prune_trees(self, trees: list) -> list:
        new_trees = []
        for tree in trees:
            if tree.get("ended_turn") is not None:
                if self.turn - tree["ended_turn"] < self.ENDED_TIMEOUT:
                    new_trees.append(tree)
            else:
                if self.turn - tree["last_used"] < self.INACTIVITY_TIMEOUT:
                    new_trees.append(tree)
        return new_trees

    def _evict_lru(self, trees: list):
        if not trees:
            return
        lru_idx = min(range(len(trees)), key=lambda i: trees[i]["last_used"])
        trees.pop(lru_idx)

    def _handle_root_match(self, group: dict, trees: list) -> tuple[str, list]:
        group_id = group["id"]
        for idx, tree in enumerate(trees):
            if tree["group_id"] == group_id:
                tree["current_nodes"] = self._get_follow_up_nodes(group_id)
                tree["last_used"] = self.turn
                tree.pop("ended_turn", None)
                trees.pop(idx)
                trees.insert(0, tree)
                return self._random_answer(group), trees

        follow_nodes = self._get_follow_up_nodes(group_id)
        if follow_nodes:
            new_tree = {
                "group_id": group_id,
                "current_nodes": follow_nodes,
                "last_used": self.turn,
                "ended_turn": None
            }
            trees.insert(0, new_tree)
            if len(trees) > self.MAX_TREES:
                self._evict_lru(trees)
        return self._random_answer(group), trees

    def get_response(self, user_input: str, state: dict = None) -> tuple[str, dict]:
        self.turn += 1
        if state is None:
            state = {}
        trees = state.get("trees", [])
        trees = [dict(t) for t in trees]

        norm_words = [_normalize_word(w) for w in user_input.split() if w]

        # 1. Match against active follow‑up trees
        candidates = []
        for ti, tree in enumerate(trees):
            if tree.get("ended_turn") is not None:
                continue
            for node in tree["current_nodes"]:
                candidates.append((node, ti))

        if candidates:
            best_score = 0
            best_node = None
            best_ti = None
            for node, ti in candidates:
                score, _ = self._best_match_in_nodes(user_input, [node])
                if score and score > best_score:
                    best_score = score
                    best_node = node
                    best_ti = ti

            if best_score >= self.threshold:
                tree = trees[best_ti]
                tree["last_used"] = self.turn
                if best_node.get("children"):
                    tree["current_nodes"] = best_node["children"]
                    tree.pop("ended_turn", None)
                else:
                    tree["current_nodes"] = []
                    tree["ended_turn"] = self.turn
                trees.pop(best_ti)
                trees.insert(0, tree)
                trees = self._prune_trees(trees)
                return self._random_answer_from_node(best_node), {"trees": trees}

        # 2. Use FTS index to find candidate groups
        candidate_group_ids = _get_group_ids_for_words(self.conn, norm_words)
        if candidate_group_ids:
            candidate_groups = self._load_groups(list(candidate_group_ids))
            score, matched_group = self._best_match_in_groups(user_input, candidate_groups)
            if matched_group:
                answer, new_trees = self._handle_root_match(matched_group, trees)
                new_trees = self._prune_trees(new_trees)
                return answer, {"trees": new_trees}

        # 3. No match at all
        trees = self._prune_trees(trees)
        return self.fallback, {"trees": trees}

def handle(text: str, state: dict = None) -> tuple[str, dict]:
    bot = RuleBot()
    try:
        response, new_state = bot.get_response(text, state)
    finally:
        bot.close()
    return response, new_state