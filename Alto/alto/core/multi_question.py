# alto/core/multi_question.py
"""
Multi‑question splitting for Alto.
Uses the existing Dispatcher and session state.
Splits if the input contains a conjunction and is not a protected phrase.
Outputs a single paragraph by concatenating answers.
"""

import re
from typing import List, Set, Optional

from rapidfuzz import fuzz

from .dispatcher import Dispatcher
from ..session import get_session, save_session


class QuestionSplitter:
    """
    Splits a user input into sub‑questions, respecting protected phrases
    (questions that are already stored in the model).
    """

    def __init__(self, dispatcher: Dispatcher, threshold: int = 70):
        self.dispatcher = dispatcher
        self.threshold = threshold
        self._protected_set: Optional[Set[str]] = None

    def _refresh_protected_set(self):
        """Build a set of normalized questions from the current model."""
        matcher = self.dispatcher.matcher
        adapter = matcher.adapter
        conn = adapter._get_conn()
        protected = set()

        # 1. Group questions (via the questions table)
        cur = conn.execute("SELECT text FROM questions")
        for row in cur:
            protected.add(self._normalize(row[0]))

        # 2. Follow‑up node questions (stored as msgpack blobs)
        cur = conn.execute("SELECT questions_blob_id FROM followup_nodes")
        for row in cur:
            blob_id = row[0]
            if blob_id and hasattr(adapter, '_decompress_blob'):
                blob_data = adapter._decompress_blob(blob_id)
                if blob_data:
                    try:
                        import msgpack
                        questions = msgpack.unpackb(blob_data, raw=False)
                        for q in questions:
                            protected.add(self._normalize(q))
                    except:
                        pass

        self._protected_set = protected

    def _normalize(self, s: str) -> str:
        s = re.sub(r'[^\w\s]', '', s)
        return ' '.join(s.lower().split())

    def is_protected(self, text: str) -> bool:
        if self._protected_set is None:
            self._refresh_protected_set()
        return self._normalize(text) in self._protected_set

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
        """Split recursively, protecting known phrases."""
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
        """Return a list of sub‑questions."""
        # If the whole text is a protected phrase, never split
        if self.is_protected(text):
            return [text]

        # Try punctuation split (., !, ?) first
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

        # Otherwise, conjunction split
        return self.split_on_conjunctions(text)


class MultiQuestionHandler:
    """
    Handles multi‑question inputs by splitting and sequentially processing
    each sub‑question, updating session state.
    Outputs a single paragraph by concatenating answers with a space.
    """

    def __init__(self, dispatcher: Dispatcher):
        self.dispatcher = dispatcher
        self.splitter = QuestionSplitter(dispatcher)

    def _ensure_punctuation(self, text: str) -> str:
        """Add a period at the end if the text doesn't end with punctuation."""
        text = text.rstrip()
        if text and text[-1] not in ('.', '!', '?'):
            text += '.'
        return text

    async def process(self, user_input: str, session_id: str, user_id: int):
        """
        Generator that yields answer chunks as a single paragraph.
        """
        state = get_session(session_id, user_id)
        full_response, new_state = self.dispatcher.process(user_input, state)
        save_session(session_id, new_state)

        # Never split if the input is a protected phrase (exact match)
        if self.splitter.is_protected(user_input):
            yield full_response
            return

        # Attempt to split regardless of confidence
        sub_questions = self.splitter.split(user_input)
        if len(sub_questions) > 1:
            current_state = state
            answers = []
            for q in sub_questions:
                if not q.strip():
                    continue
                resp, current_state = self.dispatcher.process(q, current_state)
                save_session(session_id, current_state)
                answers.append(self._ensure_punctuation(resp))
            # Join with a space to form a natural paragraph
            combined = " ".join(answers)
            yield combined
        else:
            # No split possible, just yield the original response
            yield full_response