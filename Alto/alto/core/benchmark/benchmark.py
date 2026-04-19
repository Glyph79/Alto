# alto/core/benchmark/benchmark.py
import json
import os
import time
import random
import string
from typing import Dict, List, Any, Optional, Generator, Tuple
from datetime import datetime

from ...config import RESOURCES_DIR
from ...session import get_session, save_session, set_benchmark_result

# Benchmark configuration
TYPO_PROBABILITY = 0.2
SYNONYM_PROBABILITY = 0.1
MAX_VARIATIONS_PER_QUESTION = 2

# Common typos (adjacent keys on QWERTY)
ADJACENT_KEYS = {
    'q': 'w', 'w': 'e', 'e': 'r', 'r': 't', 't': 'y', 'y': 'u', 'u': 'i', 'i': 'o', 'o': 'p',
    'a': 's', 's': 'd', 'd': 'f', 'f': 'g', 'g': 'h', 'h': 'j', 'j': 'k', 'k': 'l',
    'z': 'x', 'x': 'c', 'c': 'v', 'v': 'b', 'b': 'n', 'n': 'm'
}

class BenchmarkRunner:
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        self.matcher = dispatcher.matcher
        self.adapter = self.matcher.adapter
        self.threshold = dispatcher.threshold

    def _generate_common_typo(self, text: str) -> str:
        words = text.split()
        if not words:
            return text
        idx = random.randint(0, len(words)-1)
        word = words[idx]
        if len(word) < 3:
            return text
        
        mutation = random.choice(['transpose', 'missing', 'substitute', 'extra'])
        word_list = list(word)
        
        if mutation == 'transpose' and len(word_list) > 1:
            pos = random.randint(0, len(word_list)-2)
            word_list[pos], word_list[pos+1] = word_list[pos+1], word_list[pos]
        elif mutation == 'missing' and len(word_list) > 2:
            pos = random.randint(0, len(word_list)-1)
            del word_list[pos]
        elif mutation == 'substitute':
            pos = random.randint(0, len(word_list)-1)
            orig = word_list[pos]
            if orig.lower() in ADJACENT_KEYS:
                new_char = ADJACENT_KEYS[orig.lower()]
                if orig.isupper():
                    new_char = new_char.upper()
                word_list[pos] = new_char
            else:
                new_char = random.choice(string.ascii_lowercase)
                if orig.isupper():
                    new_char = new_char.upper()
                word_list[pos] = new_char
        elif mutation == 'extra':
            pos = random.randint(0, len(word_list))
            extra = random.choice(string.ascii_lowercase)
            if pos > 0 and word_list[pos-1].isupper():
                extra = extra.upper()
            word_list.insert(pos, extra)
        
        words[idx] = ''.join(word_list)
        return ' '.join(words)

    def _expand_with_synonyms(self, text: str) -> List[str]:
        variants_map = {}
        try:
            variants = self.adapter.get_variants()
            for vg in variants:
                words_set = set(vg['words'])
                for w in words_set:
                    variants_map[w] = words_set
        except:
            return [text]
        
        words = text.lower().split()
        variants = [text]
        for i, w in enumerate(words):
            if w in variants_map:
                for syn in variants_map[w]:
                    if syn != w:
                        new_words = words.copy()
                        new_words[i] = syn
                        variants.append(' '.join(new_words))
                        if len(variants) >= MAX_VARIATIONS_PER_QUESTION + 1:
                            break
                if len(variants) >= MAX_VARIATIONS_PER_QUESTION + 1:
                    break
        return list(set(variants))[:MAX_VARIATIONS_PER_QUESTION+1]

    def _get_node_path_questions(self, node_id: int, group_id: int) -> List[str]:
        path_questions = []
        
        def get_parent(nid):
            conn = self.adapter._get_conn()
            cur = conn.execute("SELECT parent_id FROM followup_nodes WHERE id = ?", (nid,))
            row = cur.fetchone()
            return row[0] if row else None
        
        parent = get_parent(node_id)
        while parent is not None:
            questions = self.adapter.get_node_questions(parent)
            if questions:
                path_questions.insert(0, questions[0])
            parent = get_parent(parent)
        
        group_questions = self.adapter.get_group_questions(group_id)
        if group_questions:
            path_questions.insert(0, group_questions[0])
        else:
            path_questions.insert(0, "hello")
        
        return path_questions

    def _collect_group_tests(self) -> List[Tuple[str, int, str]]:
        tests = []
        conn = self.adapter._get_conn()
        cur = conn.execute("SELECT id FROM groups ORDER BY id")
        group_ids = [row[0] for row in cur]
        
        for gid in group_ids:
            group_data = self.matcher._get_group_data(gid)
            questions = self.adapter.get_group_questions(gid)
            topic = group_data.get('topic', '')
            for q in questions:
                tests.append((q, gid, topic))
                if random.random() < TYPO_PROBABILITY:
                    typo_q = self._generate_common_typo(q)
                    if typo_q != q:
                        tests.append((typo_q, gid, topic))
                if random.random() < SYNONYM_PROBABILITY:
                    for syn_q in self._expand_with_synonyms(q):
                        if syn_q != q:
                            tests.append((syn_q, gid, topic))
                            break
        return tests

    def _collect_followup_tests(self) -> List[Tuple[str, int, int, List[str]]]:
        tests = []
        conn = self.adapter._get_conn()
        cur = conn.execute("SELECT id, group_id FROM followup_nodes ORDER BY id")
        nodes = cur.fetchall()
        for node_id, group_id in nodes:
            node_questions = self.adapter.get_node_questions(node_id)
            path_questions = self._get_node_path_questions(node_id, group_id)
            for q in node_questions:
                tests.append((q, group_id, node_id, path_questions))
                if random.random() < TYPO_PROBABILITY:
                    typo_q = self._generate_common_typo(q)
                    if typo_q != q:
                        tests.append((typo_q, group_id, node_id, path_questions))
                if random.random() < SYNONYM_PROBABILITY:
                    for syn_q in self._expand_with_synonyms(q):
                        if syn_q != q:
                            tests.append((syn_q, group_id, node_id, path_questions))
                            break
        return tests

    def _get_group_confidence(self, question: str, expected_gid: int, final_state: dict) -> float:
        gid, group_data, score = self.matcher.match_groups(question, {})
        if gid == expected_gid:
            return score
        return 0.0

    def _get_node_confidence(self, question: str, expected_nid: int, final_state: dict) -> float:
        active_trees = final_state.get("active_trees", {})
        if not active_trees:
            return 0.0
        for gid_str, tree_info in active_trees.items():
            path = tree_info.get("path", [])
            if expected_nid in path:
                from alto.core.session_tree import SessionTree
                tree = SessionTree(self.matcher, int(gid_str), path)
                candidates = tree.candidates(path)
                node, score = self.matcher.match_nodes(question, candidates)
                if node and node["id"] == expected_nid:
                    return score
                return 0.0
        return 0.0

    def run_benchmark_streaming(self) -> Generator[str, None, Dict]:
        model_name = self.dispatcher.model_name
        session_id = f"__benchmark__{model_name}"
        
        yield f"🚀 Starting benchmark on model: {model_name}\n"
        yield f"📊 Generating realistic test variations (typo prob: {TYPO_PROBABILITY*100:.0f}%, synonym prob: {SYNONYM_PROBABILITY*100:.0f}%)\n"
        
        group_tests = self._collect_group_tests()
        followup_tests = self._collect_followup_tests()
        total_tests = len(group_tests) + len(followup_tests)
        yield f"📋 {len(group_tests)} group tests + {len(followup_tests)} follow-up tests = {total_tests} total\n\n"
        
        # Get or create benchmark session
        state = get_session(session_id, None)
        state["active_trees"] = {}
        state["topics"] = {}
        save_session(session_id, state)
        
        results = []
        confidences = []
        
        if group_tests:
            yield f"🔍 TESTING GROUPS\n"
            for idx, (question, expected_gid, topic) in enumerate(group_tests, 1):
                yield f"[{idx}/{total_tests}] Group '{topic or expected_gid}' -> '{question[:60]}'\n"
                state = get_session(session_id, None)
                state["active_trees"] = {}
                state["topics"] = {}
                response, new_state = self.dispatcher.process(question, state)
                confidence = self._get_group_confidence(question, expected_gid, new_state)
                confidences.append(confidence)
                result = {
                    "type": "group",
                    "question": question,
                    "expected_group_id": expected_gid,
                    "actual_response": response,
                    "confidence": confidence,
                    "timestamp": time.time()
                }
                results.append(result)
                save_session(session_id, new_state)
                yield f"   Confidence: {confidence:.1f}% {'✅' if confidence >= self.threshold else '❌'}\n"
                yield f"   Response: {response[:100]}{'...' if len(response)>100 else ''}\n\n"
                time.sleep(0.05)
        
        if followup_tests:
            yield f"🔍 TESTING FOLLOW-UP NODES (conversation simulation)\n"
            for idx, (question, group_id, expected_nid, path_questions) in enumerate(followup_tests, len(group_tests)+1):
                yield f"[{idx}/{total_tests}] Node {expected_nid} in group {group_id} -> '{question[:60]}'\n"
                state = get_session(session_id, None)
                state["active_trees"] = {}
                state["topics"] = {}
                final_state = state
                for path_q in path_questions:
                    _, final_state = self.dispatcher.process(path_q, final_state)
                response, final_state = self.dispatcher.process(question, final_state)
                confidence = self._get_node_confidence(question, expected_nid, final_state)
                confidences.append(confidence)
                result = {
                    "type": "node",
                    "question": question,
                    "expected_node_id": expected_nid,
                    "path_questions": path_questions,
                    "actual_response": response,
                    "confidence": confidence,
                    "timestamp": time.time()
                }
                results.append(result)
                save_session(session_id, final_state)
                yield f"   Path: {' -> '.join(path_questions)}\n"
                yield f"   Confidence: {confidence:.1f}% {'✅' if confidence >= self.threshold else '❌'}\n"
                yield f"   Response: {response[:100]}{'...' if len(response)>100 else ''}\n\n"
                time.sleep(0.05)
        
        if confidences:
            high = max(confidences)
            low = min(confidences)
            avg = sum(confidences) / len(confidences)
        else:
            high = low = avg = 0
        
        final_result = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "model_name": model_name,
            "total_tests": total_tests,
            "average_confidence": avg,
            "high_confidence": high,
            "low_confidence": low,
            "threshold": self.threshold,
            "details": results
        }
        
        # Store only the latest result (overwrites previous)
        set_benchmark_result(model_name, final_result)
        
        yield f"\n📊 BENCHMARK COMPLETE\n"
        yield f"Model: {model_name}\n"
        yield f"Total test variations: {total_tests}\n\n"
        yield f"Confidence distribution: High {high:.1f}% | Low {low:.1f}%\n"
        yield f"Average confidence: {avg:.1f}%\n"
        
        return final_result