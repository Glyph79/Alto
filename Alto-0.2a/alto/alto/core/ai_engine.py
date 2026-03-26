import os
import re
import sqlite3
import msgpack
import random
import time
from fuzzywuzzy import fuzz
from collections import OrderedDict

MODELS_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")

_bot = None
_model_cache = {}
_last_scan = 0
SCAN_INTERVAL = 5

# --- Topic system constants ---
MAX_TOPICS = 3
TOPIC_DECAY = 5
TOPIC_BOOST_MAX = 20

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
    """Create group with id, name, questions, and topic name."""
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
        # Ensure all nodes in the path are loaded (for restored sessions)
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
        # Ensure the current node is loaded (it should be, but just in case)
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
        if len(self._group_cache) > 100:
            self._group_cache.popitem(last=False)
        return g

    def _update_topics(self, session_topics: dict, selected_topic: str):
        """Update topic weights: decay all, then boost selected topic."""
        # Decay all existing topics
        for t in list(session_topics.keys()):
            session_topics[t] = max(0, session_topics[t] - TOPIC_DECAY)
        # Boost selected topic
        session_topics[selected_topic] = TOPIC_BOOST_MAX
        # Remove topics with zero weight
        to_remove = [t for t, w in session_topics.items() if w == 0]
        for t in to_remove:
            del session_topics[t]
        # Keep only top MAX_TOPICS by weight
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
            # Apply topic boost from session weights
            boost = topic_weights.get(group["topic"], 0)
            final_score = base_score + boost
            print(f"  📊 Group '{group['group_name']}' (topic: '{group['topic']}') base: {base_score}, boost: {boost}, final: {final_score}")
            if final_score > best_score:
                best_score = final_score
                best_group = group
        if best_score >= self.threshold:
            return best_score, best_group
        return 0, None

    def get_response(self, text, state=None):
        if state is None:
            state = {}

        print(f"\n--- Incoming message: '{text}' ---")
        print(f"Current state: {state}")

        words = [_norm_word(w) for w in text.split() if w]
        exp = _expand_synonyms(self.conn, words)

        # Ensure topics dict exists
        if "topics" not in state:
            state["topics"] = {}

        # Step 1: Continue existing session
        if "group_id" in state and "path" in state and state["group_id"] is not None:
            gid = state["group_id"]
            path = state["path"]
            print(f"🔄 Continuing session in group {gid}, path {path}")
            tree = SessionTree(self.conn, gid, path)
            candidates = tree.candidates(path)
            print(f"  Candidate nodes: {[n.get('branch_name', n['id']) for n in candidates]}")
            score, node = self._match_score_in_nodes(text, candidates)
            if node and score >= self.threshold:
                new_path = tree.move_to(node["id"], path)
                print(f"✅ Matched node '{node.get('branch_name', 'unnamed')}' (score {score}), new path {new_path}")
                # Load answers for this node
                tree.ensure_answers(node["id"])
                # Update state with new path
                state["path"] = new_path
                return self._random_answer(node), state

        # Step 2: No active session – search all groups via FTS
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
                    # Update topics with the selected group's topic
                    if group["topic"]:
                        self._update_topics(state["topics"], group["topic"])
                    tree = SessionTree(self.conn, gid)
                    root_score, root = self._match_score_in_nodes(text, tree.roots())
                    if root and root_score >= self.threshold:
                        print(f"  ➡️ Also matched root node '{root.get('branch_name', 'unnamed')}' (score {root_score})")
                        # Load answers for this root node
                        tree.ensure_answers(root["id"])
                        state["group_id"] = gid
                        state["path"] = [root["id"]]
                        return self._random_answer(root), state
                    # No root matched – use group answer
                    if group["answers"] is None:
                        group["answers"] = _load_group_answers(self.conn, gid)
                    state["group_id"] = gid
                    state["path"] = []
                    return self._random_answer(group), state

        print("❌ No match found, using fallback")
        state["group_id"] = None
        state["path"] = []
        return self.fallback, state

    def _random_answer(self, obj):
        if obj.get("answers"):
            return random.choice(obj["answers"])
        return self.fallback

def handle(text, state=None):
    global _bot
    # Attempt to create the bot if it doesn't exist
    try:
        if _bot is None:
            _bot = RuleBot()
    except FileNotFoundError as e:
        print(f"⚠️ Model not found: {e}")
        # Return a clear error message and keep state unchanged
        return f"Model '{RuleBot.DEFAULT}' not found. Please create a model using the Alto Trainer.", state
    except Exception as e:
        print(f"⚠️ Exception while creating bot: {e}")
        return "I'm sorry, I encountered an error. Please try again later.", state

    # Use the existing bot to generate a response
    try:
        return _bot.get_response(text, state)
    except Exception as e:
        print(f"⚠️ Exception: {e}")
        # Try to recover by recreating the bot and retrying once
        try:
            _bot = RuleBot()
            return _bot.get_response(text, state)
        except Exception as e2:
            print(f"⚠️ Second exception: {e2}")
            return "I'm sorry, I encountered an error. Please try again later.", state