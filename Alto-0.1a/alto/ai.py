import os
import re
import sqlite3
import msgpack
import random
import time
from fuzzywuzzy import fuzz
from collections import OrderedDict

MODELS_BASE_DIR = os.path.join(os.path.dirname(__file__), "models")

# Global bot instance
_bot = None

# Model name -> database path cache
_model_cache = {}
_last_scan = 0
SCAN_INTERVAL = 5

def _get_db_path(model_name: str) -> str | None:
    global _last_scan
    now = time.time()
    if now - _last_scan > SCAN_INTERVAL:
        _model_cache.clear()
        if os.path.exists(MODELS_BASE_DIR):
            for entry in os.listdir(MODELS_BASE_DIR):
                folder = os.path.join(MODELS_BASE_DIR, entry)
                if not os.path.isdir(folder):
                    continue
                for f in os.listdir(folder):
                    if f.endswith('.db'):
                        path = os.path.join(folder, f)
                        try:
                            conn = sqlite3.connect(path)
                            name = conn.execute("SELECT name FROM model_info").fetchone()[0]
                            conn.close()
                            _model_cache[name] = path
                        except:
                            pass
        _last_scan = now
    return _model_cache.get(model_name)

def _unpack(data: bytes) -> list:
    return msgpack.unpackb(data, raw=False)

def _node_light(row):
    return {"id": row[0], "branch_name": row[1], "questions": _unpack(row[2]),
            "answers": None, "children": None}

def _group_light(row):
    return {"id": row[0], "group_name": row[1], "questions": _unpack(row[2]),
            "answers": None}

def _norm_word(w: str) -> str:
    return re.sub(r'[^\w\s]', '', w.lower())

def _match_score(text: str, candidates: list, key) -> tuple[int, any]:
    best_score = 0
    best = None
    text_low = text.lower()
    for c in candidates:
        for q in c.get(key, []):
            score = fuzz.token_set_ratio(text_low, q.lower())
            if score > best_score:
                best_score, best = score, c
    return best_score, best

def _expand_synonyms(conn, words: list) -> set:
    if not words:
        return set()
    expanded = set()
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

class SessionTree:
    def __init__(self, conn, group_id, turn):
        self.conn = conn
        self.group_id = group_id
        self.last_used = turn
        self._nodes = {}
        self._roots = set()
        self.path = []
        self._load_roots()

    def _load_roots(self):
        cur = self.conn.execute(
            "SELECT id, branch_name, questions_blob FROM followup_nodes "
            "WHERE group_id = ? AND parent_id IS NULL ORDER BY id", (self.group_id,)
        )
        for row in cur:
            n = _node_light(row)
            self._nodes[n["id"]] = n
            self._roots.add(n["id"])

    def _load_children(self, pid):
        cur = self.conn.execute(
            "SELECT id, branch_name, questions_blob FROM followup_nodes "
            "WHERE parent_id = ? ORDER BY id", (pid,)
        )
        kids = []
        for row in cur:
            n = _node_light(row)
            self._nodes[n["id"]] = n
            kids.append(n)
        if pid in self._nodes:
            self._nodes[pid]["children"] = kids

    def ensure_answers(self, nid):
        n = self._nodes.get(nid)
        if n and n["answers"] is None:
            cur = self.conn.execute("SELECT answers_blob FROM followup_nodes WHERE id = ?", (nid,))
            row = cur.fetchone()
            n["answers"] = _unpack(row[0]) if row else []

    def candidates(self):
        if not self.path:
            return [self._nodes[r] for r in self._roots if r in self._nodes]
        cur = self._nodes[self.path[-1]]
        if cur["children"] is None:
            self._load_children(cur["id"])
        return [self._nodes[n] for n in self.path if n in self._nodes] + (cur["children"] or [])

    def move_to(self, nid):
        if nid in self.path:
            self.path = self.path[:self.path.index(nid)+1]
        elif self.path and self._nodes[self.path[-1]].get("children"):
            if any(c["id"] == nid for c in self._nodes[self.path[-1]]["children"]):
                self.path.append(nid)
        elif nid in self._roots:
            self.path = [nid]
        else:
            self.path = [nid]

    def roots(self):
        return [self._nodes[r] for r in self._roots if r in self._nodes]

    def is_leaf(self):
        if not self.path:
            return False
        n = self._nodes[self.path[-1]]
        if n["children"] is None:
            self._load_children(n["id"])
        return not n["children"]

    def timeout(self):
        return 5 if self.is_leaf() else 10

class RuleBot:
    DEFAULT = "Alto"
    MAX_TREES = 3
    GROUP_CACHE_SIZE = 3

    def __init__(self, model=None, threshold=70):
        self.threshold = threshold
        self.fallback = "I'm sorry, I didn't understand that."
        model = model or self.DEFAULT
        path = _get_db_path(model)
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f"Model '{model}' not found")
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.row_factory = sqlite3.Row
        self._group_cache = OrderedDict()
        self._sessions = {}
        self.turn = 0

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __del__(self):
        self.close()

    def _get_group(self, gid):
        if gid in self._group_cache:
            self._group_cache.move_to_end(gid)
            return self._group_cache[gid]
        cur = self.conn.execute(
            "SELECT id, group_name, questions_blob FROM groups WHERE id = ?", (gid,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Group {gid} not found")
        g = _group_light(row)
        self._group_cache[gid] = g
        self._group_cache.move_to_end(gid)
        if len(self._group_cache) > self.GROUP_CACHE_SIZE:
            self._sessions.pop(self._group_cache.popitem(last=False)[0], None)
        return g

    def _session(self, gid):
        if gid in self._sessions:
            return self._sessions[gid]
        if len(self._sessions) >= self.MAX_TREES:
            oldest = min(self._sessions.items(), key=lambda x: x[1].last_used)[0]
            del self._sessions[oldest]
        self._sessions[gid] = SessionTree(self.conn, gid, self.turn)
        return self._sessions[gid]

    def _prune(self):
        expired = [gid for gid, s in self._sessions.items()
                   if self.turn - s.last_used > s.timeout()]
        for gid in expired:
            del self._sessions[gid]

    def get_response(self, text, state=None):
        self.turn += 1
        self._prune()
        state = state or {}
        words = [_norm_word(w) for w in text.split() if w]
        exp = _expand_synonyms(self.conn, words)

        # 1. Check existing sessions
        for gid, tree in list(self._sessions.items()):
            score, node = _match_score(text, tree.candidates(), "questions")
            if node and score >= self.threshold:
                tree.last_used = self.turn
                tree.move_to(node["id"])
                tree.ensure_answers(node["id"])
                self._get_group(gid)
                return self._random_answer(node), {"trees": []}

        # 2. FTS search with synonyms
        if exp:
            match = ' OR '.join(f'"{w}"' for w in exp)
            cur = self.conn.execute(
                "SELECT DISTINCT group_id FROM questions_fts WHERE questions_fts MATCH ?", (match,)
            )
            gids = [r[0] for r in cur]
            if gids:
                placeholders = ','.join(['?'] * len(gids))
                cur = self.conn.execute(
                    f"SELECT id, group_name, questions_blob FROM groups WHERE id IN ({placeholders})", gids
                )
                groups = [_group_light(row) for row in cur]
                score, g = _match_score(text, groups, "questions")
                if g and score >= self.threshold:
                    gid = g["id"]
                    group = self._get_group(gid)
                    tree = self._session(gid)
                    root_score, root = _match_score(text, tree.roots(), "questions")
                    if root and root_score >= self.threshold:
                        tree.last_used = self.turn
                        tree.move_to(root["id"])
                        tree.ensure_answers(root["id"])
                        return self._random_answer(root), {"trees": []}
                    # No root matched – use group answer
                    if group["answers"] is None:
                        cur = self.conn.execute("SELECT answers_blob FROM groups WHERE id = ?", (gid,))
                        row = cur.fetchone()
                        group["answers"] = _unpack(row[0]) if row else []
                    return self._random_answer(group), {"trees": []}

        return self.fallback, {"trees": []}

    def _random_answer(self, obj):
        if obj.get("answers"):
            return random.choice(obj["answers"])
        return self.fallback

def handle(text, state=None):
    global _bot
    if _bot is None:
        _bot = RuleBot()
    try:
        return _bot.get_response(text, state)
    except Exception:
        _bot = RuleBot()
        return _bot.get_response(text, state)