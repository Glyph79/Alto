import os
import re
import sqlite3
import msgpack
import random
from fuzzywuzzy import fuzz

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
        "follow_ups": _unpack_array(row[7])   # tree: list of root nodes
    }

def _normalize_word(word: str) -> str:
    return re.sub(r'[^\w\s]', '', word.lower())

def _get_word_ids(conn: sqlite3.Connection, words: list[str]) -> list[int]:
    if not words:
        return []
    placeholders = ','.join(['?'] * len(words))
    cur = conn.execute(f"SELECT id FROM words WHERE word IN ({placeholders})", words)
    return [row[0] for row in cur]

def _get_group_ids_for_words(conn: sqlite3.Connection, word_ids: list[int]) -> set[int]:
    if not word_ids:
        return set()
    placeholders = ','.join(['?'] * len(word_ids))
    cur = conn.execute(f"SELECT DISTINCT group_id FROM word_index WHERE word_id IN ({placeholders})", word_ids)
    return {row[0] for row in cur}

def _get_groups_by_ids(conn: sqlite3.Connection, group_ids: list[int]) -> list[dict]:
    if not group_ids:
        return []
    placeholders = ','.join(['?'] * len(group_ids))
    query = f"""
        SELECT id, group_name, topic, priority, section,
               questions_blob, answers_blob, follow_ups_blob
        FROM groups
        WHERE id IN ({placeholders})
    """
    cur = conn.execute(query, group_ids)
    return [_group_from_row(row) for row in cur]

class RuleBot:
    """
    Rule‑based chatbot with support for multiple concurrent follow‑up trees.
    Each tree is a nested structure of nodes (branch_name, questions, answers, children).
    When a group is first matched, only its root nodes are loaded.
    As the conversation progresses, only the relevant branch is kept in memory;
    other roots are discarded once a specific root is matched.
    Trees at a leaf have a shorter inactivity timeout (5 turns) than non‑leaf trees (10 turns).
    If the same group is matched again while its tree is still active, the match is ignored
    (no restart) to prevent going backwards – only the current nodes are considered.
    """
    DEFAULT_MODEL = "Alto"
    MAX_TREES = 3
    NORMAL_TIMEOUT = 10
    LEAF_TIMEOUT = 5

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

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __del__(self):
        self.close()

    def _best_match_in_nodes(self, user_input: str, nodes: list[dict]) -> tuple[int | None, dict | None]:
        """Find the node with the highest fuzzy match score among the given nodes."""
        best_score = 0
        best_node = None
        for node in nodes:
            for variant in node["questions"]:
                score = fuzz.ratio(user_input.lower(), variant.lower())
                if score > best_score:
                    best_score = score
                    best_node = node
        if best_score >= self.threshold:
            return best_score, best_node
        return None, None

    def _random_answer(self, node: dict) -> str:
        if node and node.get("answers"):
            return random.choice(node["answers"])
        return self.fallback

    def _get_node_by_path(self, tree: list, path: list[int]) -> dict | None:
        """
        Navigate the tree using a list of child indices and return the node at the end.
        tree: list of root nodes (each node is a dict with optional "children").
        path: list of integers, e.g. [0] for first root, [0,1] for second child of first root.
        """
        current_list = tree
        node = None
        for idx in path:
            if idx < 0 or idx >= len(current_list):
                return None
            node = current_list[idx]
            current_list = node.get("children", [])
        return node

    def get_response(self, user_input: str, state: dict) -> tuple[str, dict]:
        """
        Return (response, new_state). The state is a dictionary with:
            - "trees": list of active trees, each a dict with keys:
                "group_id": int (original group id)
                "tree": list of root nodes (only the currently relevant part of the tree)
                "current": list of paths (list of int lists) to current nodes
                "counter": int (turns since last use)
                "leaf": bool (True if this tree is currently at a leaf node)
            Trees are ordered from most recently used to least recently used.
        """
        # Copy state to avoid mutating input
        trees = [dict(t) for t in state.get("trees", [])]

        # Increment counters for all trees
        for tree in trees:
            tree["counter"] = tree.get("counter", 0) + 1

        # Tokenise input
        words = [_normalize_word(w) for w in user_input.split() if w]
        word_ids = _get_word_ids(self.conn, words)

        # ----- Try to match against active trees -----
        # Collect all current nodes across all trees with their paths and tree indices
        candidates = []  # list of (tree_index, path, node)
        for ti, t in enumerate(trees):
            for path in t.get("current", []):
                node = self._get_node_by_path(t["tree"], path)
                if node:
                    candidates.append((ti, path, node))

        if candidates:
            best_score = 0
            best_ti = None
            best_path = None
            best_node = None
            for ti, path, node in candidates:
                for variant in node["questions"]:
                    score = fuzz.ratio(user_input.lower(), variant.lower())
                    if score > best_score:
                        best_score = score
                        best_ti = ti
                        best_path = path
                        best_node = node

            if best_score >= self.threshold:
                tree = trees[best_ti]
                tree["counter"] = 0  # reset counter

                # Determine children and update tree state
                children = best_node.get("children", [])
                if children:
                    # Move to children – discard everything else
                    tree["tree"] = children          # new roots are the children
                    tree["current"] = [[i] for i in range(len(children))]
                    tree["leaf"] = False
                else:
                    # Leaf node – keep this node for possible repetition
                    tree["tree"] = [best_node]       # keep only this node
                    tree["current"] = [[0]]
                    tree["leaf"] = True

                # Move this tree to the front (most recent)
                trees.pop(best_ti)
                trees.insert(0, tree)
                return self._random_answer(best_node), {"trees": trees}

        # ----- No match in active trees → try global matching -----
        candidate_group_ids = _get_group_ids_for_words(self.conn, word_ids)
        if candidate_group_ids:
            candidate_groups = _get_groups_by_ids(self.conn, list(candidate_group_ids))
            # Convert groups to pseudo‑nodes for matching
            groups_as_nodes = []
            for g in candidate_groups:
                groups_as_nodes.append({
                    "id": g["id"],
                    "questions": g["questions"],
                    "answers": g["answers"],
                    "follow_ups": g["follow_ups"]    # full tree (roots only for now)
                })
            score, matched_node = self._best_match_in_nodes(user_input, groups_as_nodes)
            if matched_node:
                group_id = matched_node["id"]

                # If this group is already active, ignore the global match (no restart)
                if any(t.get("group_id") == group_id for t in trees):
                    # The group is already in an active tree, but its current nodes didn't match.
                    # We do not restart; just treat as no match and continue to fallback.
                    pass
                else:
                    roots = matched_node["follow_ups"]
                    # Create a new tree
                    new_tree = {
                        "group_id": group_id,
                        "tree": roots,
                        "current": [[i] for i in range(len(roots))],
                        "counter": 0,
                        "leaf": False
                    }
                    trees.insert(0, new_tree)
                    if len(trees) > self.MAX_TREES:
                        # Evict the tree with the highest counter (least recently used)
                        worst_idx = max(range(len(trees)), key=lambda i: trees[i]["counter"])
                        trees.pop(worst_idx)
                    return self._random_answer(matched_node), {"trees": trees}

        # ----- No match at all -----
        # Remove expired trees (counter >= timeout, depending on leaf status)
        new_trees = []
        for tree in trees:
            timeout = self.LEAF_TIMEOUT if tree.get("leaf", False) else self.NORMAL_TIMEOUT
            if tree["counter"] < timeout:
                new_trees.append(tree)
        return self.fallback, {"trees": new_trees}

# ----------------------------------------------------------------------
# Module‑compatible handle function
# ----------------------------------------------------------------------
def handle(text: str, state: dict) -> tuple[str, dict]:
    bot = RuleBot()
    try:
        response, new_state = bot.get_response(text, state)
    finally:
        bot.close()
    return response, new_state
