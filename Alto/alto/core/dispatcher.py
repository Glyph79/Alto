# alto/core/dispatcher.py
import time
from typing import Dict, List, Optional, Tuple
from .adapters.model import Model
from .session_tree import SessionTree
from ..config import config
from ..features import get_optional_features

DEBUG = config.getboolean('ai', 'debug', fallback=False)

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

class Dispatcher:
    def __init__(self, model_name: str, threshold: int = None):
        self.model_name = model_name
        self.threshold = threshold or config.getint('ai', 'threshold')
        self.global_fallback = config.get('DEFAULT', 'fallback')
        self.matcher = Model(model_name, self.threshold)
        self.adapter = self.matcher.adapter

        # Load optional features
        self.optional_features = []
        supported = self.adapter.get_supported_features()
        for feature_class in get_optional_features():
            if supported.get(feature_class.feature_name, False):
                self.optional_features.append(feature_class(self.adapter, config))
                debug_print(f"✅ Loaded optional feature: {feature_class.feature_name}")

    def reload(self, new_model_name: str = None):
        """Reload the model, optionally switching to a different model name."""
        if new_model_name:
            self.model_name = new_model_name
        # Recreate matcher with same threshold
        self.matcher = Model(self.model_name, self.threshold)
        self.adapter = self.matcher.adapter
        # Reload optional features
        self.optional_features = []
        supported = self.adapter.get_supported_features()
        for feature_class in get_optional_features():
            if supported.get(feature_class.feature_name, False):
                self.optional_features.append(feature_class(self.adapter, config))
                debug_print(f"✅ Reloaded optional feature: {feature_class.feature_name}")

    def _run_hook(self, hook_name: str, *args, **kwargs):
        for feature in self.optional_features:
            method = getattr(feature, hook_name, None)
            if method:
                result = method(*args, **kwargs)
                if result is not None:
                    return result
        return None

    def _update_topics(self, state: dict, selected_topic: str):
        TOPIC_DECAY = config.getint('ai', 'topic_decay')
        TOPIC_BOOST_MAX = config.getint('ai', 'topic_boost_max')
        MAX_TOPICS = config.getint('ai', 'max_topics')
        topics = state.get("topics", {})
        for t in list(topics.keys()):
            topics[t] = max(0, topics[t] - TOPIC_DECAY)
        topics[selected_topic] = TOPIC_BOOST_MAX
        to_remove = [t for t, w in topics.items() if w == 0]
        for t in to_remove:
            del topics[t]
        if len(topics) > MAX_TOPICS:
            sorted_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)
            topics = dict(sorted_topics[:MAX_TOPICS])
        state["topics"] = topics
        debug_print(f"📈 Updated topic weights: {topics}")

    def process(self, text: str, state: Dict) -> Tuple[str, Dict]:
        debug_print(f"\n--- Incoming message: '{text}' ---")
        debug_print(f"Initial state: {state}")

        # Pre‑processing
        text, state = self._run_hook("pre_process", text, state) or (text, state)

        # Step 1: Active follow‑up trees
        for gid, tree_info in list(state.get("active_trees", {}).items()):
            path = tree_info["path"]
            tree = SessionTree(self.matcher, int(gid), path)
            try:
                candidates = tree.candidates(path)
                node, score = self.matcher.match_nodes(text, candidates)
                if node and score >= self.threshold:
                    new_path = tree.move_to(node["id"], path)
                    tree.ensure_answers(node["id"])
                    state["active_trees"][gid] = {"path": new_path, "last_used": time.time()}
                    state["current_fallback_id"] = node.get("fallback_id")
                    response = node.get("answers", [self.global_fallback])[0]
                    response, state = self._run_hook("post_process", response, state) or (response, state)
                    return response, state
                else:
                    # No child matched – try custom fallback from current node
                    current_node = tree.current_node()
                    if current_node and current_node.get("fallback_id"):
                        resp = self._run_hook("get_custom_fallback", current_node["fallback_id"], state)
                        if resp:
                            state["active_trees"][gid] = {"path": path, "last_used": time.time()}
                            response, state = self._run_hook("post_process", resp, state) or (resp, state)
                            return response, state
            finally:
                tree.release()

        # Step 2: Group matching
        words = [self.matcher._norm_word(w) for w in text.split() if w]
        exp = self.adapter.expand_synonyms(words)
        if exp:
            gid, group_data, score = self.matcher.match_groups(text, state.get("topics", {}))
            if group_data and score >= self.threshold:
                if group_data.get("topic"):
                    self._update_topics(state, group_data["topic"])
                tree = SessionTree(self.matcher, group_data["id"], [])
                try:
                    node, root_score = self.matcher.match_nodes(text, tree.roots())
                    if node and root_score >= self.threshold:
                        tree.ensure_answers(node["id"])
                        state["active_trees"][str(group_data["id"])] = {"path": [node["id"]], "last_used": time.time()}
                        state["current_fallback_id"] = node.get("fallback_id")
                        response = node.get("answers", [self.global_fallback])[0]
                    else:
                        state["active_trees"][str(group_data["id"])] = {"path": [], "last_used": time.time()}
                        state["current_fallback_id"] = group_data.get("fallback_id")
                        response = group_data.get("answers", [self.global_fallback])[0]
                    response, state = self._run_hook("post_process", response, state) or (response, state)
                    return response, state
                finally:
                    tree.release()

        # Step 3: Fallback from features
        fallback_answer = self._run_hook("get_fallback_answer", state)
        if fallback_answer:
            response, state = self._run_hook("post_process", fallback_answer, state) or (fallback_answer, state)
            return response, state

        # Step 4: Global fallback
        debug_print("❌ No match found, using global fallback")
        response = self.global_fallback
        response, state = self._run_hook("post_process", response, state) or (response, state)
        return response, state