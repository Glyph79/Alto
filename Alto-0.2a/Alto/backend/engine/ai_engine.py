# Alto/backend/engine/ai_engine.py – full conversation orchestrator with custom fallbacks
import time
import re
from collections import OrderedDict
from ..config import config
from ..adapters.model import Model
from ..adapters.base import FEATURE_CUSTOM_FALLBACKS

DEBUG = config.getboolean('ai', 'debug', fallback=False)

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

class SessionTree:
    MAX_LOADED_NODES = 10

    def __init__(self, matcher, group_id, path=None):
        self.matcher = matcher          # the pure matcher (Model instance)
        self.group_id = group_id
        self._nodes = {}
        self._roots = []
        self.path = path or []
        self._loaded_nodes = OrderedDict()
        self._load_roots()

    def _load_roots(self):
        self._roots = self.matcher.adapter.get_root_nodes(self.group_id)
        for node in self._roots:
            self._nodes[node["id"]] = node

    def _load_children(self, node_id):
        children = self.matcher.adapter.get_node_children(node_id)
        if node_id in self._nodes:
            self._nodes[node_id]["children"] = children
        for child in children:
            self._nodes[child["id"]] = child

    def _ensure_questions(self, node_id):
        node = self._nodes.get(node_id)
        if not node:
            return
        if node_id in self._loaded_nodes:
            self._loaded_nodes.move_to_end(node_id)
            return
        questions = self.matcher.adapter.get_node_questions(node_id)
        node["questions"] = questions
        self._loaded_nodes[node_id] = node
        while len(self._loaded_nodes) > self.MAX_LOADED_NODES:
            oldest_id, _ = self._loaded_nodes.popitem(last=False)
            if oldest_id in self._nodes:
                self._nodes[oldest_id]["questions"] = None

    def load_questions_for_node(self, node_id):
        self._ensure_questions(node_id)

    def ensure_answers(self, node_id):
        node = self._nodes.get(node_id)
        if node and not node.get("answers_loaded"):
            answers = self.matcher.adapter.get_node_answers(node_id)
            node["answers"] = answers
            node["answers_loaded"] = True
            if node_id not in self._loaded_nodes:
                self._loaded_nodes[node_id] = node
                while len(self._loaded_nodes) > self.MAX_LOADED_NODES:
                    oldest_id, _ = self._loaded_nodes.popitem(last=False)
                    if oldest_id in self._nodes:
                        self._nodes[oldest_id]["answers"] = None
                        self._nodes[oldest_id]["answers_loaded"] = False

    def candidates(self, path):
        if not path:
            for root in self._roots:
                self._ensure_questions(root["id"])
            return self._roots
        if path[-1] not in self._nodes:
            self._nodes[path[-1]] = {"id": path[-1], "questions": None, "children": []}
        current = self._nodes[path[-1]]
        if not current.get("children"):
            self._load_children(current["id"])
        result = [self._nodes[n] for n in path if n in self._nodes] + current.get("children", [])
        for node in result:
            self._ensure_questions(node["id"])
        return result

    def move_to(self, nid, path):
        if nid in path:
            return path[:path.index(nid)+1]
        if path and self._nodes[path[-1]].get("children"):
            if any(c["id"] == nid for c in self._nodes[path[-1]]["children"]):
                return path + [nid]
        if any(r["id"] == nid for r in self._roots):
            return [nid]
        return [nid]

    def roots(self):
        return self._roots

    def current_node(self):
        if not self.path:
            return None
        return self._nodes.get(self.path[-1])


class RuleBot:
    DEFAULT = "Alto"

    def __init__(self, model=None, threshold=None):
        self.model_name = model or self.DEFAULT
        self.threshold = threshold if threshold is not None else config.getint('ai', 'threshold')
        self.fallback = config.get('DEFAULT', 'fallback')
        debug_print(f"🤖 Initializing RuleBot with model '{self.model_name}', threshold={self.threshold}")
        self.matcher = Model(self.model_name, self.threshold)
        debug_print(f"✅ Matcher loaded, version {self.matcher.get_version()}")

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

    def _evict_lru_tree(self, active_trees, max_trees):
        if len(active_trees) <= max_trees:
            return
        oldest = min(active_trees.items(), key=lambda kv: kv[1]["last_used"])
        del active_trees[oldest[0]]
        debug_print(f"🗑 Evicted LRU tree for group {oldest[0]} (max {max_trees} trees)")

    def _random_answer(self, obj):
        if obj.get("answers"):
            return obj["answers"][0]
        return self.fallback

    def _use_custom_fallback(self, fallback_id, state):
        """Try to get a custom fallback answer. Returns (answer, state) or (None, None)."""
        if not self.matcher.supports_feature(FEATURE_CUSTOM_FALLBACKS):
            return None, None
        if fallback_id:
            answers = self.matcher.get_fallback_answers(fallback_id)
            if answers:
                return answers[0], state
        return None, None

    def get_response(self, text, state=None):
        if state is None:
            state = {}

        debug_print(f"\n--- Incoming message: '{text}' ---")
        debug_print(f"Current state: {state}")

        if "topics" not in state:
            state["topics"] = {}
        if "active_trees" not in state:
            state["active_trees"] = {}
        if "current_fallback_id" not in state:
            state["current_fallback_id"] = None

        words = [self.matcher._norm_word(w) for w in text.split() if w]
        exp = self.matcher.adapter.expand_synonyms(words)
        now = time.time()
        MAX_ACTIVE_TREES = config.getint('session', 'max_active_trees')

        # Step 1: Check active trees
        debug_print(f"🔍 Checking {len(state['active_trees'])} active trees")
        for gid, tree_info in list(state["active_trees"].items()):
            path = tree_info["path"]
            debug_print(f"🔄 Checking active tree group {gid}, path {path}")
            tree = SessionTree(self.matcher, gid, path)
            candidates = tree.candidates(path)
            debug_print(f"   Candidates: {[c.get('branch_name', 'unnamed') for c in candidates]}")
            node, score = self.matcher.match_nodes(text, candidates)
            if node and score >= self.threshold:
                new_path = tree.move_to(node["id"], path)
                debug_print(f"✅ Matched node in existing tree, new path {new_path}")
                tree.ensure_answers(node["id"])
                state["active_trees"][gid] = {"path": new_path, "last_used": now}
                state["current_fallback_id"] = node.get("fallback_id")
                return self._random_answer(node), state
            else:
                # No child matched – try custom fallback of current node
                current_node = tree.current_node()
                if current_node and current_node.get("fallback_id"):
                    debug_print(f"   No child matched, using custom fallback of node '{current_node.get('branch_name', 'unnamed')}'")
                    resp, new_state = self._use_custom_fallback(current_node["fallback_id"], state)
                    if resp:
                        # Stay in the same tree, do not change path
                        state["active_trees"][gid] = {"path": path, "last_used": now}
                        return resp, state
                debug_print(f"   No child matched and no custom fallback on current node")
                # Fall through to group-level fallback later

        # Step 2: Search groups (only if no active tree matched)
        if exp:
            debug_print(f"🔎 Expanded synonyms: {exp}")
            gid, group_data, score = self.matcher.match_groups(text, state["topics"])
            if group_data:
                gid = group_data["id"]
                debug_print(f"✅ Matched group '{group_data['group_name']}' (final score {score} >= threshold {self.threshold})")
                if group_data["topic"]:
                    self._update_topics(state["topics"], group_data["topic"])
                tree = SessionTree(self.matcher, gid)
                for root in tree.roots():
                    tree.load_questions_for_node(root["id"])
                node, root_score = self.matcher.match_nodes(text, tree.roots())
                if node and root_score >= self.threshold:
                    debug_print(f"  ➡️ Also matched root node '{node.get('branch_name', 'unnamed')}' (score {root_score})")
                    tree.ensure_answers(node["id"])
                    if len(state["active_trees"]) >= MAX_ACTIVE_TREES:
                        self._evict_lru_tree(state["active_trees"], MAX_ACTIVE_TREES)
                    state["active_trees"][gid] = {"path": [node["id"]], "last_used": now}
                    state["current_fallback_id"] = node.get("fallback_id")
                    return self._random_answer(node), state
                else:
                    debug_print(f"  ➡️ No root node matched, using group answer")
                    if len(state["active_trees"]) >= MAX_ACTIVE_TREES:
                        self._evict_lru_tree(state["active_trees"], MAX_ACTIVE_TREES)
                    state["active_trees"][gid] = {"path": [], "last_used": now}
                    state["current_fallback_id"] = group_data.get("fallback_id")
                    return self._random_answer(group_data), state
            else:
                debug_print("   No group matched")
        else:
            debug_print("   No expanded synonyms to search")

        # Step 3: No match – try custom fallback from current context (group or node)
        if state.get("current_fallback_id"):
            debug_print(f"🔄 Using custom fallback from current context (fallback_id {state['current_fallback_id']})")
            resp, new_state = self._use_custom_fallback(state["current_fallback_id"], state)
            if resp:
                # Keep the current tree/path unchanged
                return resp, state

        # Step 4: Global fallback
        debug_print("❌ No match found, using global fallback")
        return self.fallback, state


# Module‑level handle function for router compatibility
_bot = None

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