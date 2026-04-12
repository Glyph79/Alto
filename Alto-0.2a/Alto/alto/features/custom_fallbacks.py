# alto/features/custom_fallbacks.py
from typing import Optional
from .base import OptionalFeature

class CustomFallbacksFeature(OptionalFeature):
    feature_name = "custom_fallbacks"

    def get_custom_fallback(self, fallback_id: int, state: dict) -> Optional[str]:
        answers = self.adapter.get_fallback_answers(fallback_id)
        if answers:
            return answers[0]
        return None

    def get_fallback_answer(self, state: dict) -> Optional[str]:
        fb_id = state.get("current_fallback_id")
        if fb_id:
            return self.get_custom_fallback(fb_id, state)
        return None