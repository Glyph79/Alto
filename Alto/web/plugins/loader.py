# web/plugins/loader.py
import os
from typing import Optional, Dict, Any, Tuple

from alto.core.plugins.interpreter import DSLInterpreter

class Plugin:
    def __init__(self, name: str, interpreter: DSLInterpreter):
        self.name = name
        self._interp = interpreter

    def process(self, user_input: str, state: dict) -> Tuple[Optional[str], dict]:
        """
        Process user input with the plugin.
        Returns (response, updated_state).
        The state dict must contain at least 'waiting_state' (if any) and 'variables'.
        """
        # Restore interpreter state
        self._interp.waiting_state = state.get("waiting_state")
        self._interp.variables = state.get("variables", {})
        response = self._interp.run(user_input)
        # Capture new state
        new_state = {
            "waiting_state": self._interp.waiting_state,
            "variables": self._interp.variables
        }
        return response, new_state

def load_plugin(plugin_name: str, plugins_dir: str) -> Optional[Plugin]:
    """Load a .plug file and return a Plugin instance."""
    plug_path = os.path.join(plugins_dir, f"{plugin_name}.plug")
    if not os.path.isfile(plug_path):
        return None
    try:
        with open(plug_path, 'r', encoding='utf-8') as f:
            code = f.read()
        interpreter = DSLInterpreter(code, verbose=False)
        return Plugin(plugin_name, interpreter)
    except Exception as e:
        print(f"Error loading plugin {plugin_name}: {e}")
        return None