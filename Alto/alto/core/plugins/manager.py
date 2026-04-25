# web/plugins/manager.py
import os
import time
from collections import OrderedDict
from typing import Optional, Tuple, List

from alto.config import RESOURCES_DIR
from .loader import load_plugin, Plugin
from .indexer import PluginIndexer

PLUGINS_DIR = os.path.join(RESOURCES_DIR, 'plugins')
MAX_ACTIVE_PLUGINS = 3

class PluginManager:
    def __init__(self):
        self._plugins_dir = PLUGINS_DIR
        os.makedirs(self._plugins_dir, exist_ok=True)
        self._indexer = PluginIndexer(self._plugins_dir)
        self._cache = OrderedDict()
        self._max_active = MAX_ACTIVE_PLUGINS

    def _ensure_index(self):
        self._indexer.rebuild_if_changed()

    def route(self, text: str) -> Optional[Tuple[str, float]]:
        self._ensure_index()
        return self._indexer.match(text)

    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        now = time.time()
        if plugin_name in self._cache:
            plugin, _ = self._cache.pop(plugin_name)
            self._cache[plugin_name] = (plugin, now)
            return plugin

        plugin = load_plugin(plugin_name, self._plugins_dir)
        if plugin is None:
            return None

        if len(self._cache) >= self._max_active:
            oldest_name, _ = self._cache.popitem(last=False)
        self._cache[plugin_name] = (plugin, now)
        return plugin

    def handle(self, text: str, session_state: dict) -> Tuple[Optional[str], dict]:
        active_plugin = session_state.get("active_plugin")
        if active_plugin:
            plugin = self.get_plugin(active_plugin)
            if plugin:
                plugin_state = session_state.get("plugin_states", {}).get(active_plugin, {})
                response, new_plugin_state = plugin.process(text, plugin_state)
                if response is not None:
                    if "plugin_states" not in session_state:
                        session_state["plugin_states"] = {}
                    session_state["plugin_states"][active_plugin] = new_plugin_state
                    if not new_plugin_state.get("waiting_state"):
                        session_state.pop("active_plugin", None)
                    return response, session_state
                else:
                    session_state.pop("active_plugin", None)

        match = self.route(text)
        if match:
            plugin_name, confidence = match
            plugin = self.get_plugin(plugin_name)
            if plugin:
                plugin_state = session_state.get("plugin_states", {}).get(plugin_name, {})
                response, new_plugin_state = plugin.process(text, plugin_state)
                if response is not None:
                    if "plugin_states" not in session_state:
                        session_state["plugin_states"] = {}
                    session_state["plugin_states"][plugin_name] = new_plugin_state
                    if new_plugin_state.get("waiting_state"):
                        session_state["active_plugin"] = plugin_name
                    return response, session_state

        return None, session_state

    def list_plugins(self) -> List[str]:
        self._ensure_index()
        return self._indexer.list_plugins()

    def reload_all(self):
        self._cache.clear()
        self._indexer.force_rebuild()