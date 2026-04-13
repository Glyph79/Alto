# alto/core/benchmark/benchmark.py
import json
import os
import time
import random
import string
from typing import Dict, List, Any, Optional, Generator, Tuple
from datetime import datetime
from rapidfuzz import fuzz

from ...config import RESOURCES_DIR

RESULTS_DIR = os.path.join(RESOURCES_DIR, 'results')

# Benchmark configuration
TYPO_PROBABILITY = 0.2          # 20% of questions get a typo
SYNONYM_PROBABILITY = 0.1       # 10% get a synonym variant
MAX_VARIATIONS_PER_QUESTION = 2  # Max additional variants per original question

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
        self._ensure_dirs()

    def _ensure_dirs(self):
        os.makedirs(RESULTS_DIR, exist_ok=True)

    def _generate_common_typo(self, text: str) -> str:
        """Introduce a realistic typo (transposition, missing, substitution, extra)."""
        words = text.split()
        if not words:
            return text
        # Pick a random word
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
                # fallback to random letter
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
        """Replace one word with a synonym if available."""
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

    def _collect_group_tests(self) -> List[Tuple[str, int, str]]:
        """Generate test cases from group questions, with limited variations."""
        tests = []
        conn = self.adapter._get_conn()
        cur = conn.execute("SELECT id FROM groups ORDER BY id")
        group_ids = [row[0] for row in cur]
        
        for gid in group_ids:
            group_data = self.matcher._get_group_data(gid)
            questions = self.adapter.get_group_questions(gid)
            topic = group_data.get('topic', '')
            for q in questions:
                # Original question
                tests.append((q, gid, topic))
                # Typo variant (probabilistic)
                if random.random() < TYPO_PROBABILITY:
                    typo_q = self._generate_common_typo(q)
                    if typo_q != q:
                        tests.append((typo_q, gid, topic))
                # Synonym variant (probabilistic)
                if random.random() < SYNONYM_PROBABILITY:
                    for syn_q in self._expand_with_synonyms(q):
                        if syn_q != q:
                            tests.append((syn_q, gid, topic))
                            break  # only one synonym variant per question
        return tests

    def _collect_followup_tests(self) -> List[Tuple[str, int, int]]:
        """Generate test cases from follow-up node questions, with limited variations."""
        tests = []
        conn = self.adapter._get_conn()
        cur = conn.execute("SELECT id, group_id FROM followup_nodes ORDER BY id")
        nodes = cur.fetchall()
        for node_id, group_id in nodes:
            node_questions = self.adapter.get_node_questions(node_id)
            for q in node_questions:
                tests.append((q, group_id, node_id))
                if random.random() < TYPO_PROBABILITY:
                    typo_q = self._generate_common_typo(q)
                    if typo_q != q:
                        tests.append((typo_q, group_id, node_id))
                if random.random() < SYNONYM_PROBABILITY:
                    for syn_q in self._expand_with_synonyms(q):
                        if syn_q != q:
                            tests.append((syn_q, group_id, node_id))
                            break
        return tests

    def _score_group_match(self, question: str, expected_gid: int, actual_state: dict) -> float:
        active_trees = actual_state.get("active_trees", {})
        if not active_trees:
            return 0.0
        matched_gid_str = next(iter(active_trees.keys()))
        matched_gid = int(matched_gid_str)
        return 100.0 if matched_gid == expected_gid else 0.0

    def _score_node_match(self, question: str, expected_nid: int, actual_state: dict) -> float:
        active_trees = actual_state.get("active_trees", {})
        if not active_trees:
            return 0.0
        tree_info = next(iter(active_trees.values()))
        path = tree_info.get("path", [])
        if path and path[-1] == expected_nid:
            return 100.0
        return 0.0

    def run_benchmark_streaming(self) -> Generator[str, None, Dict]:
        yield f"🚀 Starting benchmark on model: {self.dispatcher.model_name}\n"
        yield f"📊 Generating realistic test variations (typo prob: {TYPO_PROBABILITY*100:.0f}%, synonym prob: {SYNONYM_PROBABILITY*100:.0f}%)...\n"
        
        group_tests = self._collect_group_tests()
        followup_tests = self._collect_followup_tests()
        total_tests = len(group_tests) + len(followup_tests)
        yield f"📋 {len(group_tests)} group tests + {len(followup_tests)} follow-up tests = {total_tests} total\n\n"
        
        results = []
        scores = []
        
        if group_tests:
            yield f"🔍 TESTING GROUPS\n"
            for idx, (question, expected_gid, topic) in enumerate(group_tests, 1):
                yield f"[{idx}/{total_tests}] Group '{topic or expected_gid}' -> '{question[:60]}'\n"
                temp_state = {"topics": {}, "active_trees": {}}
                response, new_state = self.dispatcher.process(question, temp_state)
                score = self._score_group_match(question, expected_gid, new_state)
                scores.append(score)
                results.append({
                    "type": "group",
                    "question": question,
                    "expected_group_id": expected_gid,
                    "actual_response": response,
                    "score": score
                })
                yield f"   Score: {score:.1f}% {'✅' if score >= 70 else '❌'}\n"
                yield f"   Response: {response[:100]}{'...' if len(response)>100 else ''}\n\n"
                time.sleep(0.05)
        
        if followup_tests:
            yield f"🔍 TESTING FOLLOW-UP NODES\n"
            for idx, (question, group_id, expected_nid) in enumerate(followup_tests, len(group_tests)+1):
                yield f"[{idx}/{total_tests}] Node {expected_nid} in group {group_id} -> '{question[:60]}'\n"
                temp_state = {"topics": {}, "active_trees": {}}
                response, new_state = self.dispatcher.process(question, temp_state)
                score = self._score_node_match(question, expected_nid, new_state)
                scores.append(score)
                results.append({
                    "type": "node",
                    "question": question,
                    "expected_node_id": expected_nid,
                    "actual_response": response,
                    "score": score
                })
                yield f"   Score: {score:.1f}% {'✅' if score >= 70 else '❌'}\n"
                yield f"   Response: {response[:100]}{'...' if len(response)>100 else ''}\n\n"
                time.sleep(0.05)
        
        if scores:
            high = max(scores)
            low = min(scores)
            avg = sum(scores) / len(scores)
            correct_count = sum(1 for s in scores if s >= 70)
            accuracy = (correct_count / len(scores)) * 100
        else:
            high = low = avg = correct_count = accuracy = 0
        
        final_result = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "model_name": self.dispatcher.model_name,
            "total_tests": total_tests,
            "correct": correct_count,
            "accuracy": accuracy,
            "high_score": high,
            "low_score": low,
            "average_score": avg,
            "details": results
        }
        
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_path = os.path.join(RESULTS_DIR, f"benchmark_{timestamp_str}.json")
        with open(result_path, 'w') as f:
            json.dump(final_result, f, indent=2)
        latest_path = os.path.join(RESULTS_DIR, "latest.json")
        with open(latest_path, 'w') as f:
            json.dump(final_result, f, indent=2)
        
        yield f"\n📊 BENCHMARK COMPLETE\n"
        yield f"Model: {self.dispatcher.model_name}\n"
        yield f"Total test variations: {total_tests}\n"
        yield f"Correct (score ≥70%): {correct_count} ({accuracy:.1f}%)\n"
        yield f"Score distribution:\n"
        yield f"  🔥 High: {high:.1f}%\n"
        yield f"  📉 Low:  {low:.1f}%\n"
        yield f"  📈 Average: {avg:.1f}%\n"
        yield f"Results saved to resources/results/\n"
        
        return final_result

    def get_latest_results(self) -> Optional[Dict]:
        latest_path = os.path.join(RESULTS_DIR, "latest.json")
        if os.path.exists(latest_path):
            with open(latest_path, 'r') as f:
                return json.load(f)
        return None