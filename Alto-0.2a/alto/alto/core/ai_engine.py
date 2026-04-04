import os
import re
import json
import tarfile
import tempfile
import hashlib
import sqlite3
import time
import msgpack
import sys
from collections import OrderedDict
from fuzzywuzzy import fuzz
from alto.config import config

# Current version of the Alto AI engine (must match trainer's ALTO_VERSION)
ALTO_VERSION = "0.2a"

MODELS_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")
# Cache directory for extracted databases (separate from trainer's temp dir)
CACHE_ROOT = os.path.join(tempfile.gettempdir(), "alto_cache")
os.makedirs(CACHE_ROOT, exist_ok=True)

# --- Helpers for container handling (self-contained) ---
def safe_filename(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)

def find_model_dir(model_name: str):
    """Find the folder containing the model's .rbm container (or legacy .db)."""
    safe = safe_filename(model_name)
    if not os.path.exists(MODELS_BASE_DIR):
        return None
    for entry in os.listdir(MODELS_BASE_DIR):
        full_path = os.path.join(MODELS_BASE_DIR, entry)
        if not os.path.isdir(full_path):
            continue
        if entry.endswith('_' + safe):
            return entry
    return None

def get_model_container_path(model_name: str):
    folder = find_model_dir(model_name)
    if not folder:
        return None
    safe = safe_filename(model_name)
    candidate = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.rbm")
    if os.path.isfile(candidate):
        return candidate
    # fallback: any .rbm in the folder
    for f in os.listdir(os.path.join(MODELS_BASE_DIR, folder)):
        if f.endswith('.rbm'):
            return os.path.join(MODELS_BASE_DIR, folder, f)
    return None

def get_legacy_db_path(model_name: str):
    """Find a legacy .db file (old format)."""
    folder = find_model_dir(model_name)
    if not folder:
        return None
    safe = safe_filename(model_name)
    candidate = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.db")
    if os.path.isfile(candidate):
        return candidate
    # fallback: any .db in the folder
    for f in os.listdir(os.path.join(MODELS_BASE_DIR, folder)):
        if f.endswith('.db'):
            return os.path.join(MODELS_BASE_DIR, folder, f)
    return None

def read_manifest(container_path: str):
    try:
        with tarfile.open(container_path, 'r') as tar:
            member = tar.getmember('manifest.json')
            with tar.extractfile(member) as f:
                return json.load(f)
    except:
        return None

def get_cached_db_path(model_name: str) -> str:
    """
    Returns a path to an extracted database file for the model.
    Prefers .rbm container; falls back to legacy .db with warning.
    """
    container_path = get_model_container_path(model_name)
    if container_path and os.path.isfile(container_path):
        # Use container
        mtime = os.path.getmtime(container_path)
        key = hashlib.md5(f"{model_name}_{mtime}".encode()).hexdigest()[:16]
        cache_dir = os.path.join(CACHE_ROOT, model_name, key)
        db_path = os.path.join(cache_dir, "database.db")
        if os.path.isfile(db_path) and os.path.getmtime(db_path) >= mtime:
            return db_path
        os.makedirs(cache_dir, exist_ok=True)
        with tarfile.open(container_path, 'r') as tar:
            tar.extractall(cache_dir)
        if not os.path.isfile(db_path):
            raise RuntimeError(f"Extraction failed: {db_path} missing")
        return db_path

    # Fallback to legacy .db
    legacy_path = get_legacy_db_path(model_name)
    if legacy_path and os.path.isfile(legacy_path):
        print(f"⚠️ Model '{model_name}' is using the old .db format. "
              "Please convert it to the new .rbm format using the Alto Trainer for better compatibility.",
              file=sys.stderr)
        return legacy_path

    raise FileNotFoundError(f"Model '{model_name}' not found (no .rbm or .db)")

def get_db_alto_version(db_path: str) -> str | None:
    """Read alto_version from the database, return None if not found."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.execute("SELECT alto_version FROM model_info")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None

# --- Original AI engine code below, with modifications ---
def _get_db_path(model_name: str) -> str | None:
    """Return path to a read‑only database (extracted from .rbm or legacy .db)."""
    try:
        db_path = get_cached_db_path(model_name)
        # Check version compatibility
        db_version = get_db_alto_version(db_path)
        if db_version and db_version != ALTO_VERSION:
            print(f"⚠️ Model '{model_name}' was created with Alto version {db_version}, "
                  f"but the current engine is version {ALTO_VERSION}. "
                  "Some features may not work correctly.",
                  file=sys.stderr)
        return db_path
    except FileNotFoundError:
        return None

def _unpack(data: bytes) -> list:
    return msgpack.unpackb(data, raw=False)

def _node_light(row):
    return {"id": row[0], "branch_name": row[1], "questions": _unpack(row[2]),
            "answers": None, "children": None}

def _group_light(row):
    return {
        "id": row[0],
        "group_name": row[1],
        "topic": row[2] if row[2] is not None else "",
        "questions": _unpack(row[3]),
        "answers": None
    }

def _norm_word(w: str) -> str:
    return re.sub(r'[^\w\s]', '', w.lower())

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

def _load_node_answers(conn, node_id):
    cur = conn.execute("SELECT answers_blob FROM followup_nodes WHERE id = ?", (node_id,))
    row = cur.fetchone()
    return _unpack(row[0]) if row else []

def _load_group_answers(conn, group_id):
    cur = conn.execute("SELECT answers_blob FROM groups WHERE id = ?", (group_id,))
    row = cur.fetchone()
    return _unpack(row[0]) if row else []

class SessionTree:
    def __init__(self, conn, group_id, path=None):
        self.conn = conn
        self.group_id = group_id
        self._nodes = {}
        self._roots = set()
        self._load_roots()
        self.path = path or []
        for node_id in self.path:
            if node_id not in self._nodes:
                cur = self.conn.execute(
                    "SELECT id, branch_name, questions_blob FROM followup_nodes WHERE id = ?",
                    (node_id,)
                )
                row = cur.fetchone()
                if row:
                    n = _node_light(row)
                    self._nodes[node_id] = n

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
            n["answers"] = _load_node_answers(self.conn, nid)

    def candidates(self, path):
        if not path:
            return [self._nodes[r] for r in self._roots if r in self._nodes]
        if path[-1] not in self._nodes:
            cur = self.conn.execute(
                "SELECT id, branch_name, questions_blob FROM followup_nodes WHERE id = ?",
                (path[-1],)
            )
            row = cur.fetchone()
            if row:
                n = _node_light(row)
                self._nodes[path[-1]] = n
        current = self._nodes[path[-1]]
        if current["children"] is None:
            self._load_children(current["id"])
        return [self._nodes[n] for n in path if n in self._nodes] + (current["children"] or [])

    def move_to(self, nid, path):
        if nid in path:
            return path[:path.index(nid)+1]
        if path and self._nodes[path[-1]].get("children"):
            if any(c["id"] == nid for c in self._nodes[path[-1]]["children"]):
                return path + [nid]
        if nid in self._roots:
            return [nid]
        return [nid]

    def roots(self):
        return [self._nodes[r] for r in self._roots if r in self._nodes]

class RuleBot:
    DEFAULT = "Alto"
    GROUP_CACHE_SIZE = 3

    def __init__(self, model=None, threshold=None):
        self.conn = None
        self.threshold = threshold if threshold is not None else config.getint('ai', 'threshold')
        self.fallback = config.get('DEFAULT', 'fallback')
        model = model or self.DEFAULT
        db_path = _get_db_path(model)
        if not db_path or not os.path.isfile(db_path):
            raise FileNotFoundError(f"Model '{model}' not found")
        # Open database read-only
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        self.conn.execute("PRAGMA query_only = 1")
        self.conn.row_factory = sqlite3.Row
        self._group_cache = OrderedDict()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __del__(self):
        self.close()

    def _get_group_light(self, gid):
        if gid in self._group_cache:
            self._group_cache.move_to_end(gid)
            return self._group_cache[gid]
        cur = self.conn.execute(
            """SELECT g.id, g.group_name, COALESCE(t.name, '') as topic,
                      g.questions_blob
               FROM groups g
               LEFT JOIN topics t ON g.topic_id = t.id
               WHERE g.id = ?""",
            (gid,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Group {gid} not found")
        g = _group_light(row)
        self._group_cache[gid] = g
        self._group_cache.move_to_end(gid)
        if len(self._group_cache) > self.GROUP_CACHE_SIZE:
            self._group_cache.popitem(last=False)
        return g

    def _update_topics(self, session_topics: dict, selected_topic: str):
        TOPIC_DECAY = config.getint('ai', 'topic_decay')
        TOPIC_BOOST_MAX = config.getint('ai', 'topic_boost_max')
        MAX_TOPICS = config.getint('ai', 'max_topics')
        for t in list(session_topics.keys()):
            session_topics[t] = max(0, session_topics[t] - TOPIC_DECAY)
        session_topics[selected_topic] = TOPIC_BOOST_MAX
        to_remove = [t for t, w in session_topics.items() if w == 0]
        for t in to_remove:
            del session_topics[t]
        if len(session_topics) > MAX_TOPICS:
            sorted_topics = sorted(session_topics.items(), key=lambda x: x[1], reverse=True)
            new_topics = dict(sorted_topics[:MAX_TOPICS])
            session_topics.clear()
            session_topics.update(new_topics)
        print(f"📈 Updated topic weights: {session_topics}")

    def _match_score_in_nodes(self, text: str, nodes: list) -> tuple[int, dict | None]:
        best_score = 0
        best_node = None
        text_low = text.lower()
        for node in nodes:
            for q in node.get("questions", []):
                score = fuzz.token_set_ratio(text_low, q.lower())
                if score > best_score:
                    best_score = score
                    best_node = node
        if best_node:
            print(f"  📌 Node '{best_node.get('branch_name', 'unnamed')}' score: {best_score}")
        if best_score >= self.threshold:
            return best_score, best_node
        return 0, None

    def _match_score_in_groups(self, text: str, groups: list, topic_weights: dict) -> tuple[int, dict | None]:
        best_score = 0
        best_group = None
        text_low = text.lower()
        for group in groups:
            base_score = 0
            for q in group["questions"]:
                score = fuzz.token_set_ratio(text_low, q.lower())
                if score > base_score:
                    base_score = score
            boost = topic_weights.get(group["topic"], 0)
            final_score = base_score + boost
            print(f"  📊 Group '{group['group_name']}' (topic: '{group['topic']}') base: {base_score}, boost: {boost}, final: {final_score}")
            if final_score > best_score:
                best_score = final_score
                best_group = group
        if best_score >= self.threshold:
            return best_score, best_group
        return 0, None

    def _evict_lru_tree(self, active_trees: dict, max_trees: int):
        if len(active_trees) <= max_trees:
            return
        oldest = min(active_trees.items(), key=lambda kv: kv[1]["last_used"])
        del active_trees[oldest[0]]
        print(f"🗑 Evicted LRU tree for group {oldest[0]} (max {max_trees} trees)")

    def get_response(self, text, state=None):
        if state is None:
            state = {}

        print(f"\n--- Incoming message: '{text}' ---")
        print(f"Current state: {state}")

        if "topics" not in state:
            state["topics"] = {}
        if "active_trees" not in state:
            state["active_trees"] = {}

        words = [_norm_word(w) for w in text.split() if w]
        exp = _expand_synonyms(self.conn, words)
        now = time.time()
        MAX_ACTIVE_TREES = config.getint('session', 'max_active_trees')

        # Step 1: Check all active trees for a match
        for gid, tree_info in list(state["active_trees"].items()):
            path = tree_info["path"]
            print(f"🔄 Checking active tree group {gid}, path {path}")
            tree = SessionTree(self.conn, gid, path)
            candidates = tree.candidates(path)
            score, node = self._match_score_in_nodes(text, candidates)
            if node and score >= self.threshold:
                new_path = tree.move_to(node["id"], path)
                print(f"✅ Matched node in existing tree, new path {new_path}")
                tree.ensure_answers(node["id"])
                state["active_trees"][gid] = {"path": new_path, "last_used": now}
                return self._random_answer(node), state

        # Step 2: No active tree matched – search all groups via FTS
        if exp:
            match = ' OR '.join(f'"{w}"' for w in exp)
            cur = self.conn.execute(
                "SELECT DISTINCT group_id FROM questions_fts WHERE questions_fts MATCH ?", (match,)
            )
            gids = [r[0] for r in cur]
            if gids:
                placeholders = ','.join(['?'] * len(gids))
                cur = self.conn.execute(
                    f"""SELECT g.id, g.group_name, COALESCE(t.name, '') as topic,
                               g.questions_blob
                        FROM groups g
                        LEFT JOIN topics t ON g.topic_id = t.id
                        WHERE g.id IN ({placeholders})""",
                    gids
                )
                groups = [_group_light(row) for row in cur]
                print("🔎 Searching groups...")
                score, group = self._match_score_in_groups(text, groups, state["topics"])
                if group and score >= self.threshold:
                    gid = group["id"]
                    print(f"✅ Matched group '{group['group_name']}' (final score {score})")
                    if group["topic"]:
                        self._update_topics(state["topics"], group["topic"])
                    tree = SessionTree(self.conn, gid)
                    root_score, root = self._match_score_in_nodes(text, tree.roots())
                    if root and root_score >= self.threshold:
                        print(f"  ➡️ Also matched root node '{root.get('branch_name', 'unnamed')}' (score {root_score})")
                        tree.ensure_answers(root["id"])
                        if len(state["active_trees"]) >= MAX_ACTIVE_TREES:
                            self._evict_lru_tree(state["active_trees"], MAX_ACTIVE_TREES)
                        state["active_trees"][gid] = {"path": [root["id"]], "last_used": now}
                        return self._random_answer(root), state
                    else:
                        if group["answers"] is None:
                            group["answers"] = _load_group_answers(self.conn, gid)
                        if len(state["active_trees"]) >= MAX_ACTIVE_TREES:
                            self._evict_lru_tree(state["active_trees"], MAX_ACTIVE_TREES)
                        state["active_trees"][gid] = {"path": [], "last_used": now}
                        return self._random_answer(group), state

        print("❌ No match found, using fallback")
        return self.fallback, state

    def _random_answer(self, obj):
        if obj.get("answers"):
            return obj["answers"][0]  # deterministic first answer
        return self.fallback

def handle(text, state=None):
    global _bot
    try:
        if _bot is None:
            _bot = RuleBot()
    except FileNotFoundError as e:
        print(f"⚠️ Model not found: {e}")
        return f"Model '{RuleBot.DEFAULT}' not found. Please create a model using the Alto Trainer.", state
    except Exception as e:
        print(f"⚠️ Exception while creating bot: {e}")
        return "I'm sorry, I encountered an error. Please try again later.", state

    try:
        return _bot.get_response(text, state)
    except Exception as e:
        print(f"⚠️ Exception: {e}")
        try:
            _bot = RuleBot()
            return _bot.get_response(text, state)
        except Exception as e2:
            print(f"⚠️ Second exception: {e2}")
            return "I'm sorry, I encountered an error. Please try again later.", state

_bot = None