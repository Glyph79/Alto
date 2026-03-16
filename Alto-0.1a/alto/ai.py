import os
import re
import sqlite3
import msgpack
import random
from fuzzywuzzy import fuzz
from collections import OrderedDict

MODELS_BASE_DIR = os.path.join(os.path.dirname(__file__), "models")

# Global bot instance (persists across calls)
_bot = None

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
    safe = _safe_filename(model_name)
    return os.path.join(MODELS_BASE_DIR, folder, f"{safe}.db")

def _unpack_array(data: bytes) -> list:
    return msgpack.unpackb(data, raw=False)

def _node_from_row_light(row: sqlite3.Row) -> dict:
    """Create node with only id, branch_name, questions; answers = None."""
    return {
        "id": row[0],
        "branch_name": row[1],
        "questions": _unpack_array(row[2]),
        "answers": None,
        "children": None
    }

def _group_from_row_light(row: sqlite3.Row) -> dict:
    """Create group with only metadata and questions; answers = None."""
    return {
        "id": row[0],
        "group_name": row[1],
        "topic": row[2],
        "priority": row[3],
        "section": row[4],
        "questions": _unpack_array(row[5]),
        "answers": None
    }

def _normalize_word(word: str) -> str:
    return re.sub(r'[^\w\s]', '', word.lower())

def _get_group_ids_for_words(conn: sqlite3.Connection, words: list[str]) -> set[int]:
    if not words:
        return set()
    match_expr = ' OR '.join(f'"{w}"' for w in words)
    cur = conn.execute(
        "SELECT DISTINCT group_id FROM questions_fts WHERE questions_fts MATCH ?",
        (match_expr,)
    )
    return {row[0] for row in cur}

def _get_group_light_by_ids(conn: sqlite3.Connection, group_ids: list[int]) -> list[dict]:
    if not group_ids:
        return []
    placeholders = ','.join(['?'] * len(group_ids))
    query = f"""
        SELECT id, group_name, topic, priority, section,
               questions_blob
        FROM groups
        WHERE id IN ({placeholders})
    """
    cur = conn.execute(query, group_ids)
    return [_group_from_row_light(row) for row in cur]

def _load_node_answers(conn: sqlite3.Connection, node_id: int) -> list:
    cur = conn.execute("SELECT answers_blob FROM followup_nodes WHERE id = ?", (node_id,))
    row = cur.fetchone()
    return _unpack_array(row[0]) if row else []

def _load_group_answers(conn: sqlite3.Connection, group_id: int) -> list:
    cur = conn.execute("SELECT answers_blob FROM groups WHERE id = ?", (group_id,))
    row = cur.fetchone()
    return _unpack_array(row[0]) if row else []

class SessionTree:
    def __init__(self, conn: sqlite3.Connection, group_id: int, turn: int):
        self.conn = conn
        self.group_id = group_id
        self.last_used_turn = turn

        self._node_cache = {}          # node_id -> node dict (light, answers=None)
        self._root_ids = set()
        self.path = []

        self._load_roots()

    def _load_roots(self):
        cur = self.conn.execute(
            "SELECT id, branch_name, questions_blob FROM followup_nodes "
            "WHERE group_id = ? AND parent_id IS NULL ORDER BY id",
            (self.group_id,)
        )
        for row in cur:
            node = _node_from_row_light(row)
            node_id = node["id"]
            node["children"] = None
            self._node_cache[node_id] = node
            self._root_ids.add(node_id)

    def _load_children(self, node_id: int):
        cur = self.conn.execute(
            "SELECT id, branch_name, questions_blob FROM followup_nodes "
            "WHERE parent_id = ? ORDER BY id",
            (node_id,)
        )
        children = []
        for row in cur:
            node = _node_from_row_light(row)
            child_id = node["id"]
            node["children"] = None
            self._node_cache[child_id] = node
            children.append(node)
        if node_id in self._node_cache:
            self._node_cache[node_id]["children"] = children

    def ensure_node_answers(self, node_id: int):
        node = self._node_cache.get(node_id)
        if node and node["answers"] is None:
            node["answers"] = _load_node_answers(self.conn, node_id)

    def get_candidate_nodes(self) -> list[dict]:
        candidates = []
        if not self.path:
            candidates = [self._node_cache[nid] for nid in self._root_ids if nid in self._node_cache]
        else:
            for node_id in self.path:
                if node_id in self._node_cache:
                    candidates.append(self._node_cache[node_id])
            current_id = self.path[-1]
            if current_id in self._node_cache:
                current = self._node_cache[current_id]
                if current["children"] is None:
                    self._load_children(current_id)
                candidates.extend(current["children"])
        return candidates

    def move_to_node(self, node_id: int):
        if node_id in self.path:
            idx = self.path.index(node_id)
            self.path = self.path[:idx+1]
            return
        if self.path:
            current_id = self.path[-1]
            if current_id in self._node_cache:
                current = self._node_cache[current_id]
                if current["children"] is None:
                    self._load_children(current_id)
                if any(child["id"] == node_id for child in current["children"]):
                    self.path.append(node_id)
                    return
        if node_id in self._root_ids:
            self.path = [node_id]
            return
        self.path = [node_id]

    def get_roots(self) -> list[dict]:
        return [self._node_cache[nid] for nid in self._root_ids if nid in self._node_cache]

    def is_leaf(self) -> bool:
        if not self.path:
            return False
        current_id = self.path[-1]
        if current_id not in self._node_cache:
            return False
        current = self._node_cache[current_id]
        if current["children"] is None:
            self._load_children(current_id)
        return len(current["children"]) == 0

    def get_timeout(self) -> int:
        return 5 if self.is_leaf() else 10

class RuleBot:
    DEFAULT_MODEL = "Alto"
    MAX_TREES = 3
    GROUP_CACHE_SIZE = 3

    def __init__(self, model_name: str | None = None, threshold: int = 70):
        self.threshold = threshold
        self.fallback = "I'm sorry, I didn't understand that."

        model = model_name or self.DEFAULT_MODEL
        db_path = _get_model_db_path(model)
        if not db_path or not os.path.isfile(db_path):
            raise FileNotFoundError(f"Model '{model}' not found or database missing")

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.row_factory = sqlite3.Row

        self._group_cache = OrderedDict()   # group_id -> group dict (light)
        self._session_trees: dict[int, SessionTree] = {}

        self.turn = 0

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __del__(self):
        self.close()

    def _get_group_light(self, group_id: int) -> dict:
        """Get group with questions only (answers None)."""
        if group_id in self._group_cache:
            self._group_cache.move_to_end(group_id)
            return self._group_cache[group_id]

        cur = self.conn.execute(
            "SELECT id, group_name, topic, priority, section, "
            "questions_blob FROM groups WHERE id = ?",
            (group_id,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Group id {group_id} not found")
        group = _group_from_row_light(row)

        self._group_cache[group_id] = group
        self._group_cache.move_to_end(group_id)
        if len(self._group_cache) > self.GROUP_CACHE_SIZE:
            oldest_id, _ = self._group_cache.popitem(last=False)
            self._session_trees.pop(oldest_id, None)

        return group

    def _get_session_tree(self, group_id: int) -> SessionTree | None:
        return self._session_trees.get(group_id)

    def _create_session_tree(self, group_id: int) -> SessionTree:
        tree = SessionTree(self.conn, group_id, self.turn)
        self._session_trees[group_id] = tree

        if len(self._session_trees) > self.MAX_TREES:
            oldest_id = min(self._session_trees.items(), key=lambda x: x[1].last_used_turn)[0]
            del self._session_trees[oldest_id]

        return tree

    def _prune_session_trees(self):
        expired = []
        for gid, tree in self._session_trees.items():
            timeout = tree.get_timeout()
            if self.turn - tree.last_used_turn > timeout:
                expired.append(gid)
        for gid in expired:
            del self._session_trees[gid]

    def _best_match_in_nodes(self, user_input: str, nodes: list[dict]) -> tuple[int | None, dict | None]:
        best_score = 0
        best_node = None
        user_lower = user_input.lower()
        for node in nodes:
            for q in node.get("questions", []):
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

    def _random_answer(self, group_or_node: dict) -> str:
        if group_or_node and group_or_node.get("answers"):
            return random.choice(group_or_node["answers"])
        return self.fallback

    def get_response(self, user_input: str, state: dict = None) -> tuple[str, dict]:
        self.turn += 1
        if state is None:
            state = {}

        self._prune_session_trees()

        norm_words = [_normalize_word(w) for w in user_input.split() if w]

        # 1. Check existing sessions
        for gid, tree in list(self._session_trees.items()):
            candidates = tree.get_candidate_nodes()
            if not candidates:
                continue
            score, matched_node = self._best_match_in_nodes(user_input, candidates)
            if matched_node:
                tree.last_used_turn = self.turn
                tree.move_to_node(matched_node['id'])
                tree.ensure_node_answers(matched_node['id'])   # load answers now
                # group might already be in cache; if not, load light
                self._get_group_light(gid)
                return self._random_answer(matched_node), {"trees": []}

        # 2. Search all groups via FTS
        candidate_group_ids = _get_group_ids_for_words(self.conn, norm_words)
        if candidate_group_ids:
            candidate_groups = _get_group_light_by_ids(self.conn, list(candidate_group_ids))
            score, matched_group = self._best_match_in_groups(user_input, candidate_groups)
            if matched_group:
                gid = matched_group["id"]
                group = self._get_group_light(gid)   # light version already in cache
                tree = self._get_session_tree(gid)
                if not tree:
                    tree = self._create_session_tree(gid)
                root_score, matched_root = self._best_match_in_nodes(user_input, tree.get_roots())
                if matched_root:
                    tree.last_used_turn = self.turn
                    tree.move_to_node(matched_root['id'])
                    tree.ensure_node_answers(matched_root['id'])
                    return self._random_answer(matched_root), {"trees": []}
                # No root matched – use group answer
                if group["answers"] is None:
                    group["answers"] = _load_group_answers(self.conn, gid)
                return self._random_answer(group), {"trees": []}

        return self.fallback, {"trees": []}

def handle(text: str, state: dict = None) -> tuple[str, dict]:
    global _bot
    if _bot is None:
        _bot = RuleBot()
    try:
        response, new_state = _bot.get_response(text, state)
    except Exception:
        _bot = RuleBot()
        response, new_state = _bot.get_response(text, state)
    return response, new_state
    