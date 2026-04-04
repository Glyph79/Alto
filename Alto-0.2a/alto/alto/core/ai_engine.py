import os
import re
import time
import sqlite3
import msgpack
from collections import OrderedDict
from fuzzywuzzy import fuzz
from alto.config import config
from alto.loaders import get_loader

DEBUG = True   # set to False to disable debug prints

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

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
    debug_print(f"🔍 Expanded synonyms: {words} -> {expanded}")
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
        self.model_name = model or self.DEFAULT
        debug_print(f"🤖 Initializing RuleBot with model '{self.model_name}', threshold={self.threshold}")
        loader = get_loader(self.model_name)
        self.conn = loader.get_connection(self.model_name)
        debug_print(f"✅ Loader {loader.get_version()} provided connection")
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
        debug_print(f"📈 Updated topic weights: {session_topics}")

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
            debug_print(f"  📌 Node '{best_node.get('branch_name', 'unnamed')}' score: {best_score}")
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
            debug_print(f"  📊 Group '{group['group_name']}' (topic: '{group['topic']}') base: {base_score}, boost: {boost}, final: {final_score}")
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
        debug_print(f"🗑 Evicted LRU tree for group {oldest[0]} (max {max_trees} trees)")

    def get_response(self, text, state=None):
        if state is None:
            state = {}

        debug_print(f"\n--- Incoming message: '{text}' ---")
        debug_print(f"Current state: {state}")

        if "topics" not in state:
            state["topics"] = {}
        if "active_trees" not in state:
            state["active_trees"] = {}

        words = [_norm_word(w) for w in text.split() if w]
        exp = _expand_synonyms(self.conn, words)
        now = time.time()
        MAX_ACTIVE_TREES = config.getint('session', 'max_active_trees')

        # Step 1: Check all active trees for a match
        debug_print(f"🔍 Checking {len(state['active_trees'])} active trees")
        for gid, tree_info in list(state["active_trees"].items()):
            path = tree_info["path"]
            debug_print(f"🔄 Checking active tree group {gid}, path {path}")
            tree = SessionTree(self.conn, gid, path)
            candidates = tree.candidates(path)
            debug_print(f"   Candidates: {[c.get('branch_name', 'unnamed') for c in candidates]}")
            score, node = self._match_score_in_nodes(text, candidates)
            if node and score >= self.threshold:
                new_path = tree.move_to(node["id"], path)
                debug_print(f"✅ Matched node in existing tree, new path {new_path}")
                tree.ensure_answers(node["id"])
                state["active_trees"][gid] = {"path": new_path, "last_used": now}
                return self._random_answer(node), state

        # Step 2: No active tree matched – search all groups via FTS
        if exp:
            match = ' OR '.join(f'"{w}"' for w in exp)
            debug_print(f"🔎 FTS query: {match}")
            cur = self.conn.execute(
                "SELECT DISTINCT group_id FROM questions_fts WHERE questions_fts MATCH ?", (match,)
            )
            gids = [r[0] for r in cur]
            debug_print(f"   FTS returned {len(gids)} group IDs: {gids}")
            if gids:
                placeholders = ','.join(['?'] * len(gids))
                query = f"""SELECT g.id, g.group_name, COALESCE(t.name, '') as topic,
                                  g.questions_blob
                           FROM groups g
                           LEFT JOIN topics t ON g.topic_id = t.id
                           WHERE g.id IN ({placeholders})"""
                cur = self.conn.execute(query, gids)
                groups = [_group_light(row) for row in cur]
                debug_print(f"   Loaded {len(groups)} groups")
                debug_print(f"   Current topic weights: {state['topics']}")
                score, group = self._match_score_in_groups(text, groups, state["topics"])
                if group and score >= self.threshold:
                    gid = group["id"]
                    debug_print(f"✅ Matched group '{group['group_name']}' (final score {score} >= threshold {self.threshold})")
                    if group["topic"]:
                        self._update_topics(state["topics"], group["topic"])
                    tree = SessionTree(self.conn, gid)
                    root_score, root = self._match_score_in_nodes(text, tree.roots())
                    if root and root_score >= self.threshold:
                        debug_print(f"  ➡️ Also matched root node '{root.get('branch_name', 'unnamed')}' (score {root_score})")
                        tree.ensure_answers(root["id"])
                        if len(state["active_trees"]) >= MAX_ACTIVE_TREES:
                            self._evict_lru_tree(state["active_trees"], MAX_ACTIVE_TREES)
                        state["active_trees"][gid] = {"path": [root["id"]], "last_used": now}
                        return self._random_answer(root), state
                    else:
                        debug_print(f"  ➡️ No root node matched, using group answer")
                        if group["answers"] is None:
                            group["answers"] = _load_group_answers(self.conn, gid)
                        if len(state["active_trees"]) >= MAX_ACTIVE_TREES:
                            self._evict_lru_tree(state["active_trees"], MAX_ACTIVE_TREES)
                        state["active_trees"][gid] = {"path": [], "last_used": now}
                        return self._random_answer(group), state
                else:
                    debug_print(f"   No group matched with score >= {self.threshold} (best score: {score})")
            else:
                debug_print("   FTS returned no matching groups")
        else:
            debug_print("   No expanded synonyms to search with FTS")

        debug_print("❌ No match found, using fallback")
        return self.fallback, state

    def _random_answer(self, obj):
        if obj.get("answers"):
            return obj["answers"][0]
        return self.fallback

def handle(text, state=None):
    global _bot
    try:
        if _bot is None:
            debug_print("🔄 Creating new RuleBot instance")
            _bot = RuleBot()
    except FileNotFoundError as e:
        debug_print(f"⚠️ Model not found: {e}")
        return f"Model '{RuleBot.DEFAULT}' not found. Please create a model using the Alto Trainer.", state
    except Exception as e:
        debug_print(f"⚠️ Exception while creating bot: {e}")
        return "I'm sorry, I encountered an error. Please try again later.", state

    try:
        return _bot.get_response(text, state)
    except Exception as e:
        debug_print(f"⚠️ Exception: {e}")
        try:
            _bot = RuleBot()
            return _bot.get_response(text, state)
        except Exception as e2:
            debug_print(f"⚠️ Second exception: {e2}")
            return "I'm sorry, I encountered an error. Please try again later.", state

_bot = None