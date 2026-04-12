# alto/features/base.py
from abc import ABC, abstractmethod

class OptionalFeature(ABC):
    feature_name: str = "base"

    def __init__(self, adapter, config):
        self.adapter = adapter
        self.config = config

    def pre_process(self, text: str, state: dict):
        return None

    def on_group_match(self, group_data: dict, state: dict):
        return None

    def on_node_match(self, node_data: dict, state: dict):
        return None

    def get_fallback_answer(self, state: dict):
        return None

    def post_process(self, response: str, state: dict):
        return None

    def get_custom_fallback(self, fallback_id: int, state: dict):
        return None