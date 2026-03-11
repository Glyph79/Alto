# router.py
import importlib
from fuzzywuzzy import fuzz

# ========== CONFIGURATION ==========
ROUTER_THRESHOLD = 60   # Minimum confidence to activate a module
# ====================================

# Define routes: each entry maps a list of phrase variants to a module name
ROUTES = [
    {
        "variants": [
            "weather", "what's the weather", "what is the weather",
            "forecast", "temperature", "rain", "weather today", "weather tomorrow"
        ],
        "module": "weather"
    },
    # Add more routes here
]

class Router:
    def __init__(self):
        self.modules = {}  # cache loaded modules

    def _load_module(self, module_name):
        """Dynamically import a module from the 'modules' package."""
        if module_name in self.modules:
            return self.modules[module_name]
        try:
            module = importlib.import_module(f"modules.{module_name}")
            self.modules[module_name] = module
            return module
        except ImportError as e:
            print(f"--- Router: could not load module '{module_name}': {e}")
            return None

    def route(self, text: str, state: dict):
        """
        Return (module, confidence) for this message, considering state.
        If state has 'current_module', that module wins (forced routing).
        """
        # 1. If a module has claimed the conversation, use it unconditionally
        if "current_module" in state:
            module_name = state["current_module"]
            module = self._load_module(module_name)
            if module:
                return module, 100  # high confidence to override

        # 2. Otherwise, fuzzy match against ROUTES
        best_score = 0
        best_module_name = None
        text_lower = text.lower()

        for route in ROUTES:
            for variant in route["variants"]:
                score = fuzz.partial_ratio(text_lower, variant.lower())
                if score > best_score:
                    best_score = score
                    best_module_name = route["module"]

        print(f"--- Router best match: '{best_module_name}' with score {best_score}")

        if best_score >= ROUTER_THRESHOLD and best_module_name:
            module = self._load_module(best_module_name)
            return module, best_score
        return None, 0

    def handle(self, text: str, state: dict):
        """
        Route the message and call the chosen module's handle().
        Returns (response, updated_state).
        """
        module, conf = self.route(text, state)
        if module:
            print(f"--- Router: routed to '{module.__name__}' with confidence {conf}")
            try:
                # Module handle must accept (text, state) and return (response, new_state)
                return module.handle(text, state)
            except Exception as e:
                print(f"--- Router: module '{module.__name__}' raised error: {e}")
                # Fallback to ai.py
                from ai import handle as fallback_handle
                return fallback_handle(text, state)
        else:
            print("--- Router: no module matched, falling back to ai.py")
            from ai import handle as fallback_handle
            return fallback_handle(text, state)

# Singleton instance
router = Router()