# alto/core/dispatcher.py
import time
import random
import json
from typing import Dict, List, Optional, Tuple, Any
from .adapters.model import Model
from .session_tree import SessionTree
from ..config import config
from ..features import get_optional_features
from .jit_cache import JITCache

DEBUG = config.getboolean('ai', 'debug', fallback=False)
ENABLE_JIT = config.getboolean('ai', 'enable_jit_cache', fallback=True)

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

        self.jit_cache = JITCache() if ENABLE_JIT else None
        if self.jit_cache:
            jit_ram_mode = config.getboolean('ai', 'jit_ram_only_mode', fallback=True)
            self.jit_cache.set_ram_mode(jit_ram_mode)

        self.optional_features = []
        supported = self.adapter.get_supported_features()
        for feature_class in get_optional_features():
            if supported.get(feature_class.feature_name, False):
                self.optional_features.append(feature_class(self.adapter, config))
                debug_print(f"✅ Loaded optional feature: {feature_class.feature_name}")

    def reload(self, new_model_name: str = None):
        if new_model_name:
            self.model_name = new_model_name
        self.matcher = Model(self.model_name, self.threshold)
        self.adapter = self.matcher.adapter
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

    def _get_context_signature(self, state: dict) -> str:
        parts = []
        topics = state.get("topics", {})
        if topics:
            sorted_topics = sorted((t, w) for t, w in topics.items() if w > 0)
            parts.append("t:" + ",".join(f"{t}={w}" for t, w in sorted_topics))
        active_trees = state.get("active_trees", {})
        if active_trees:
            gid_str, tree_info = next(iter(active_trees.items()))
            path = tree_info.get("path", [])
            parts.append(f"g:{gid_str},p:{','.join(str(n) for n in path)}")
        return ";".join(parts) if parts else ""

    def _pick_random_answer(self, answers: List[str]) -> str:
        if not answers:
            return self.global_fallback
        return random.choice(answers)

    # --------------------- REBAKE SUPPORT ---------------------
    def rebake_jit(self, rebake_type: str = "all") -> str:
        """Rebuild JIT cache entries by re‑evaluating against current model.
        rebake_type: "typo", "exact", or "all"
        """
        if not self.jit_cache:
            return "JIT cache not enabled."

        results = {"typo": {"kept": 0, "updated": 0, "deleted": 0},
                   "exact": {"kept": 0, "updated": 0, "deleted": 0}}

        # ---- Typo rebake ----
        if rebake_type in ("typo", "all"):
            for wrong, old_correct, _ in self.jit_cache.iter_typo_entries():
                # Check if the wrong word now exists as a question word (exact match or in any group's questions)
                if self._is_word_valid(wrong):
                    self.jit_cache.delete_typo(wrong)
                    results["typo"]["deleted"] += 1
                else:
                    # Keep the existing correction (we cannot recompute a better one without full sentence)
                    results["typo"]["kept"] += 1

        # ---- Exact rebake ----
        if rebake_type in ("exact", "all"):
            for key, response_json, _ in self.jit_cache.iter_exact_entries():
                try:
                    sentence, context_sig = key.split('\x00', 1)
                except ValueError:
                    # malformed key
                    self.jit_cache.delete_exact(key)
                    results["exact"]["deleted"] += 1
                    continue

                # Reconstruct session state from context signature
                state = self._state_from_context_signature(context_sig)

                # Simulate a cache miss: run matching without JIT cache
                try:
                    new_ref = self._simulate_cache_miss(sentence, state)
                except Exception as e:
                    debug_print(f"Error during rebake for key {key}: {e}")
                    new_ref = None

                stored_ref = json.loads(response_json)

                if new_ref is None:
                    # No match in current model -> delete entry
                    self.jit_cache.delete_exact(key)
                    results["exact"]["deleted"] += 1
                elif new_ref == stored_ref:
                    results["exact"]["kept"] += 1
                else:
                    self.jit_cache.update_exact(key, new_ref)
                    results["exact"]["updated"] += 1

        return (f"Rebake complete:\n"
                f"Typo: kept {results['typo']['kept']}, updated {results['typo']['updated']}, deleted {results['typo']['deleted']}\n"
                f"Exact: kept {results['exact']['kept']}, updated {results['exact']['updated']}, deleted {results['exact']['deleted']}")

    def _is_word_valid(self, word: str) -> bool:
        """Check if a word appears in any group question (exact match)."""
        try:
            conn = self.matcher.adapter._get_conn()
            cur = conn.execute("SELECT 1 FROM questions WHERE text LIKE ? LIMIT 1", (f'%{word}%',))
            return cur.fetchone() is not None
        except:
            return False

    def _state_from_context_signature(self, sig: str) -> dict:
        """Reconstruct minimal session state from context signature."""
        state = {"topics": {}, "active_trees": {}}
        parts = sig.split(';')
        for part in parts:
            if part.startswith('t:'):
                topics_str = part[2:]
                for item in topics_str.split(','):
                    if '=' in item:
                        t, w = item.split('=')
                        state["topics"][t] = int(w)
            elif part.startswith('g:'):
                rest = part[2:]
                if ',p:' in rest:
                    gid_str, path_str = rest.split(',p:', 1)
                    path = [int(n) for n in path_str.split(',')] if path_str else []
                    state["active_trees"][gid_str] = {"path": path, "last_used": time.time()}
        return state

    def _simulate_cache_miss(self, text: str, state: dict) -> Optional[dict]:
        """Run matching pipeline without JIT cache, return reference that would be stored."""
        original_cache = self.jit_cache
        self.jit_cache = None   # temporarily disable
        try:
            ref = self._match_and_get_reference(text, state)
            return ref
        finally:
            self.jit_cache = original_cache

    def _match_and_get_reference(self, text: str, state: dict) -> Optional[dict]:
        """Simulate matching and return the reference that would be cached, or None."""
        # Typo correction (if jit_cache is None, correct_sentence will still work but without cache)
        corrected_text = self.matcher.correct_sentence(text)

        # Follow-up trees
        for gid, tree_info in list(state.get("active_trees", {}).items()):
            path = tree_info["path"]
            tree = SessionTree(self.matcher, int(gid), path)
            try:
                candidates = tree.candidates(path)
                node, score = self.matcher.match_nodes(corrected_text, candidates)
                if node and score >= self.threshold:
                    return {"type": "node", "id": node["id"], "group_id": int(gid)}
                else:
                    current_node = tree.current_node()
                    if current_node and current_node.get("fallback_id"):
                        # store current node as reference
                        return {"type": "node", "id": current_node["id"], "group_id": int(gid)}
            finally:
                tree.release()

        # Group matching
        words = [self.matcher._norm_word(w) for w in corrected_text.split() if w]
        exp = self.adapter.expand_synonyms(words)
        if exp:
            gid, group_data, score = self.matcher.match_groups(corrected_text, state.get("topics", {}))
            if group_data and score >= self.threshold:
                tree = SessionTree(self.matcher, group_data["id"], [])
                try:
                    node, root_score = self.matcher.match_nodes(corrected_text, tree.roots())
                    if node and root_score >= self.threshold:
                        return {"type": "node", "id": node["id"], "group_id": group_data["id"]}
                    else:
                        return {"type": "group", "id": group_data["id"]}
                finally:
                    self.matcher.cache.release_group(group_data["id"])

        # Feature fallback (do not cache)
        fallback_answer = self._run_hook("get_fallback_answer", state)
        if fallback_answer:
            return None

        # Global fallback
        return None

    # --------------------- MAIN PROCESSING ---------------------
    def process(self, text: str, state: Dict) -> Tuple[str, Dict]:
        start_time = time.perf_counter()
        debug_print(f"\n--- Incoming message: '{text}' ---")
        debug_print(f"Initial state: {state}")

        text, state = self._run_hook("pre_process", text, state) or (text, state)

        # ----- 1. WORD CORRECTIONS -----
        if self.jit_cache:
            corrected_text = self.matcher.correct_sentence(text)
            if corrected_text != text:
                debug_print(f"🔧 Corrected sentence: '{text}' -> '{corrected_text}'")
            else:
                debug_print(f"📝 No correction needed for '{text}'")
        else:
            corrected_text = text

        # ----- 2. DATABASE EXACT MATCH -----
        try:
            conn = self.matcher.adapter._get_conn()
            cur = conn.execute(
                "SELECT q.id, gq.group_id FROM questions q "
                "JOIN group_questions gq ON gq.question_id = q.id "
                "WHERE q.text = ? LIMIT 1",
                (corrected_text,)
            )
            row = cur.fetchone()
            if row:
                group_id = row[1]
                group_data = self.matcher._get_group_data(group_id)
                response = self._pick_random_answer(group_data.get("answers", []))
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                print(f"[TIMING] Database exact match: {elapsed_ms:.2f} ms")
                debug_print(f"📄 Database exact match for '{corrected_text}' -> group {group_id}")
                response, state = self._run_hook("post_process", response, state) or (response, state)
                return response, state
        except Exception as e:
            debug_print(f"Database exact match error: {e}")

        # ----- 3. JIT CACHE (REFERENCE‑BASED) -----
        if self.jit_cache:
            normalized_text = self.matcher.normalize_variants(corrected_text)
            context_sig = self._get_context_signature(state)
            ref = self.jit_cache.get_exact(normalized_text, context_sig)
            if ref:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                print(f"[TIMING] JIT exact cache hit (reference): {elapsed_ms:.2f} ms")
                debug_print(f"⚡ Cache hit for normalized '{normalized_text}' (ref={ref})")

                if ref["type"] == "node":
                    node_id = ref["id"]
                    group_id = ref.get("group_id")
                    node_data = self.matcher.get_node_data(node_id)
                    if not group_id:
                        group_id = node_data.get("group_id")
                    if group_id:
                        state["active_trees"][str(group_id)] = {"path": [node_id], "last_used": time.time()}
                    response = self._pick_random_answer(node_data.get("answers", []))
                elif ref["type"] == "group":
                    group_id = ref["id"]
                    group_data = self.matcher._get_group_data(group_id)
                    state["active_trees"][str(group_id)] = {"path": [], "last_used": time.time()}
                    response = self._pick_random_answer(group_data.get("answers", []))
                else:
                    response = self.global_fallback

                response, state = self._run_hook("post_process", response, state) or (response, state)
                return response, state

        # ----- 4. FOLLOW‑UP TREES -----
        for gid, tree_info in list(state.get("active_trees", {}).items()):
            path = tree_info["path"]
            tree = SessionTree(self.matcher, int(gid), path)
            try:
                candidates = tree.candidates(path)
                node, score = self.matcher.match_nodes(corrected_text, candidates)
                if node and score >= self.threshold:
                    new_path = tree.move_to(node["id"], path)
                    tree.ensure_answers(node["id"])
                    state["active_trees"][gid] = {"path": new_path, "last_used": time.time()}
                    state["current_fallback_id"] = node.get("fallback_id")
                    if self.jit_cache:
                        ref = {"type": "node", "id": node["id"], "group_id": int(gid)}
                        normalized = self.matcher.normalize_variants(corrected_text)
                        self.jit_cache.set_exact(normalized, ref, self._get_context_signature(state))
                    node_questions = node.get("questions", [])
                    if node_questions:
                        self.matcher.learn_typos_from_match(text, node_questions[0])
                    response = self._pick_random_answer(node.get("answers", []))
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    print(f"[TIMING] Follow-up tree match: {elapsed_ms:.2f} ms")
                    response, state = self._run_hook("post_process", response, state) or (response, state)
                    return response, state
                else:
                    current_node = tree.current_node()
                    if current_node and current_node.get("fallback_id"):
                        resp = self._run_hook("get_custom_fallback", current_node["fallback_id"], state)
                        if resp:
                            state["active_trees"][gid] = {"path": path, "last_used": time.time()}
                            if self.jit_cache:
                                ref = {"type": "node", "id": current_node["id"], "group_id": int(gid)}
                                normalized = self.matcher.normalize_variants(corrected_text)
                                self.jit_cache.set_exact(normalized, ref, self._get_context_signature(state))
                            elapsed_ms = (time.perf_counter() - start_time) * 1000
                            print(f"[TIMING] Follow-up fallback: {elapsed_ms:.2f} ms")
                            response, state = self._run_hook("post_process", resp, state) or (resp, state)
                            return response, state
            finally:
                tree.release()

        # ----- 5. GROUP MATCHING -----
        words = [self.matcher._norm_word(w) for w in corrected_text.split() if w]
        exp = self.adapter.expand_synonyms(words)
        if exp:
            gid, group_data, score = self.matcher.match_groups(corrected_text, state.get("topics", {}))
            if group_data and score >= self.threshold:
                if group_data.get("topic"):
                    self._update_topics(state, group_data["topic"])
                tree = SessionTree(self.matcher, group_data["id"], [])
                try:
                    node, root_score = self.matcher.match_nodes(corrected_text, tree.roots())
                    if node and root_score >= self.threshold:
                        tree.ensure_answers(node["id"])
                        state["active_trees"][str(group_data["id"])] = {"path": [node["id"]], "last_used": time.time()}
                        state["current_fallback_id"] = node.get("fallback_id")
                        response = self._pick_random_answer(node.get("answers", []))
                        node_questions = node.get("questions", [])
                        if node_questions:
                            self.matcher.learn_typos_from_match(text, node_questions[0])
                        if self.jit_cache:
                            ref = {"type": "node", "id": node["id"], "group_id": group_data["id"]}
                            normalized = self.matcher.normalize_variants(corrected_text)
                            self.jit_cache.set_exact(normalized, ref, self._get_context_signature(state))
                    else:
                        state["active_trees"][str(group_data["id"])] = {"path": [], "last_used": time.time()}
                        state["current_fallback_id"] = group_data.get("fallback_id")
                        response = self._pick_random_answer(group_data.get("answers", []))
                        group_questions = self.adapter.get_group_questions(group_data["id"])
                        if group_questions:
                            self.matcher.learn_typos_from_match(text, group_questions[0])
                        if self.jit_cache:
                            ref = {"type": "group", "id": group_data["id"]}
                            normalized = self.matcher.normalize_variants(corrected_text)
                            self.jit_cache.set_exact(normalized, ref, self._get_context_signature(state))
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    print(f"[TIMING] Group match (fuzzy): {elapsed_ms:.2f} ms")
                    response, state = self._run_hook("post_process", response, state) or (response, state)
                    return response, state
                finally:
                    self.matcher.cache.release_group(group_data["id"])

        # ----- 6. FEATURE FALLBACK -----
        fallback_answer = self._run_hook("get_fallback_answer", state)
        if fallback_answer:
            response = fallback_answer
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            print(f"[TIMING] Feature fallback: {elapsed_ms:.2f} ms")
            response, state = self._run_hook("post_process", response, state) or (response, state)
            return response, state

        # ----- 7. GLOBAL FALLBACK -----
        debug_print("❌ No match found, using global fallback")
        response = self.global_fallback
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        print(f"[TIMING] Global fallback: {elapsed_ms:.2f} ms")
        response, state = self._run_hook("post_process", response, state) or (response, state)
        return response, state