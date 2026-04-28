# alto/core/multi_question.py
"""
Multi‑question splitting for Alto.
Now includes comparison detection (difference between, compare, vs, etc.)
Outputs a natural paragraph with "while" for comparisons.
"""

import re
from functools import lru_cache
from typing import List, Optional, Tuple

from .dispatcher import Dispatcher
from ..session import get_session, save_session


class QuestionSplitter:
    def __init__(self, dispatcher: Dispatcher, threshold: int = 70):
        self.dispatcher = dispatcher
        self.threshold = threshold
        # LRU cache for normalized protected questions – avoids loading all questions into memory
        self._protected_cache_maxsize = 5000   # can be overridden via config later
        self._is_protected_cached = lru_cache(maxsize=self._protected_cache_maxsize)(
            self._check_protected
        )

    def _normalize(self, s: str) -> str:
        s = re.sub(r'[^\w\s]', '', s)
        return ' '.join(s.lower().split())

    def _check_protected(self, norm: str) -> bool:
        """
        Query the database to see if a normalized question exists.
        Only checks the main `questions` table (group questions) because:
        - Follow‑up node questions are already processed by the dispatcher before splitting.
        - If a follow‑up question exactly matches, the dispatcher handles it and we never reach the splitter.
        - Skipping follow‑up questions saves memory and is safe.
        """
        matcher = self.dispatcher.matcher
        adapter = matcher.adapter
        conn = adapter._get_conn()

        # For v0.1a and v0.2a, the `questions` table stores all group questions.
        # We use a direct equality check on the normalized form.
        # Assuming an index exists on `text` (or we can use lower() if needed).
        cur = conn.execute(
            "SELECT 1 FROM questions WHERE lower(replace(text, '.', '')) = ? LIMIT 1",
            (norm,)
        )
        return cur.fetchone() is not None

    def is_protected(self, text: str) -> bool:
        """Return True if the exact normalized text exists as a group question."""
        norm = self._normalize(text)
        return self._is_protected_cached(norm)

    def looks_like_question(self, text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return False
        first = lowered.split()[0]
        question_words = {"what", "how", "why", "when", "where", "who", "which"}
        modals = {"can", "could", "would", "should", "may", "might", "must"}
        verbs = {"is", "are", "was", "were", "do", "does", "did", "have", "has"}
        command_verbs = {"tell", "explain", "describe", "show", "give", "list", "name"}
        return (first in question_words or
                first in modals or
                first in verbs or
                first in command_verbs)

    def split_on_conjunctions(self, text: str) -> List[str]:
        conjunctions = [" and ", " then ", " also "]
        best_split = None
        best_score = -1
        for conj in conjunctions:
            pos = 0
            while True:
                idx = text.find(conj, pos)
                if idx == -1:
                    break
                left = text[:idx].strip()
                right = text[idx + len(conj):].strip()
                if left and right and self.looks_like_question(left) and self.looks_like_question(right):
                    score = 0
                    if self.is_protected(left):
                        score += 100
                    if self.is_protected(right):
                        score += 50
                    score += len(left) + len(right)
                    if score > best_score:
                        best_score = score
                        best_split = (left, right)
                pos = idx + 1
        if best_split:
            left, right = best_split
            left_parts = self.split_on_conjunctions(left) if left else []
            right_parts = self.split_on_conjunctions(right) if right else []
            return (left_parts if left_parts else [left]) + (right_parts if right_parts else [right])
        else:
            return [text]

    def split(self, text: str) -> List[str]:
        if self.is_protected(text):
            return [text]
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', text.strip())
        if len(sentences) > 1:
            result = []
            for sent in sentences:
                sent = sent.strip()
                if self.is_protected(sent):
                    result.append(sent)
                else:
                    result.extend(self.split_on_conjunctions(sent))
            return result
        return self.split_on_conjunctions(text)


class MultiQuestionHandler:
    def __init__(self, dispatcher: Dispatcher):
        self.dispatcher = dispatcher
        self.splitter = QuestionSplitter(dispatcher)

    def _ensure_punctuation(self, text: str) -> str:
        text = text.rstrip()
        if text and text[-1] not in ('.', '!', '?'):
            text += '.'
        return text

    def _extract_comparison(self, text: str) -> Optional[Tuple[str, str]]:
        patterns = [
            r"difference between ([^.?!]+?) and ([^.?!]+)",
            r"compare ([^.?!]+?) and ([^.?!]+)",
            r"([^.?!]+?) vs ([^.?!]+)",
            r"how is ([^.?!]+?) different from ([^.?!]+)",
            r"what is the difference between ([^.?!]+?) and ([^.?!]+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text.lower())
            if m:
                a = m.group(1).strip()
                b = m.group(2).strip()
                a = re.sub(r'[.!?]$', '', a)
                b = re.sub(r'[.!?]$', '', b)
                a = re.sub(r'[^a-z0-9\s_]', '', a)
                b = re.sub(r'[^a-z0-9\s_]', '', b)
                if a and b:
                    return a, b
        return None

    def _get_concept_answer(self, concept: str, state: dict) -> str:
        query = f"what is {concept}"
        ans, _ = self.dispatcher.process(query, state)
        concept_lower = concept.lower()
        if concept_lower not in ans.lower() or "I'm sorry" in ans:
            query2 = f"tell me about {concept}"
            ans2, _ = self.dispatcher.process(query2, state)
            if concept_lower in ans2.lower() and "I'm sorry" not in ans2:
                ans = ans2
            else:
                return f"I don't have specific information about '{concept}'."
        return self._ensure_punctuation(ans)

    async def process(self, user_input: str, session_id: str, user_id: int):
        state = get_session(session_id, user_id)

        # 1. Check for comparison first
        comparison = self._extract_comparison(user_input)
        if comparison:
            item_a, item_b = comparison
            ans_a = self._get_concept_answer(item_a, state)
            ans_b = self._get_concept_answer(item_b, state)

            if ans_a.startswith("I don't have") and ans_b.startswith("I don't have"):
                response = f"I don't have information about '{item_a}' or '{item_b}'."
            elif ans_a.startswith("I don't have"):
                response = f"I don't know about '{item_a}', but regarding '{item_b}': {ans_b}"
            elif ans_b.startswith("I don't have"):
                response = f"I don't know about '{item_b}', but regarding '{item_a}': {ans_a}"
            else:
                # Remove trailing punctuation from both answers for cleaner joining
                a_clean = ans_a.rstrip('.!?')
                b_clean = ans_b.rstrip('.!?')
                # Ensure proper capitalization
                a_clean = a_clean[0].upper() + a_clean[1:] if a_clean else a_clean
                b_clean = b_clean[0].lower() + b_clean[1:] if b_clean else b_clean
                response = f"{a_clean}, while {b_clean}."
            yield response
            save_session(session_id, state)
            return

        # 2. Normal multi‑question handling
        full_response, new_state = self.dispatcher.process(user_input, state)
        save_session(session_id, new_state)

        if self.splitter.is_protected(user_input):
            yield full_response
            return

        sub_questions = self.splitter.split(user_input)

        # Deduplicate consecutive identical sub‑questions
        deduped = []
        last = None
        for q in sub_questions:
            if q != last:
                deduped.append(q)
                last = q
        sub_questions = deduped

        if len(sub_questions) > 1:
            current_state = state
            answers = []
            for q in sub_questions:
                if not q.strip():
                    continue
                resp, current_state = self.dispatcher.process(q, current_state)
                save_session(session_id, current_state)
                answers.append(self._ensure_punctuation(resp))
            combined = " ".join(answers)
            yield combined
        else:
            yield full_response