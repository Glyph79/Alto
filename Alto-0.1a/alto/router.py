import importlib
from fuzzywuzzy import fuzz

# ========== CONFIGURATION ==========
ROUTER_THRESHOLD = 60   # Minimum confidence to activate a module
# ====================================

# Define routes: each entry maps a list of phrase variants to a module name
ROUTES = [
    {
        "variants": [
            "weather", 
            "what's the weather", 
            "what is the weather",
            "forecast", 
            "temperature", 
            "rain",
            "weather today",
            "weather tomorrow"
        ],
        "module": "weather"
    },
    # Add more routes as needed
]

class Router:
    """
    Routes an English message to the appropriate module based on fuzzy matching.
    """
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

    def route(self, text):
        """
        Find the best matching module for the given text.
        Returns (module, confidence) where module is the loaded module object,
        or (None, 0) if no match meets the threshold.
        """
        best_score = 0
        best_module_name = None
        text_lower = text.lower()
        
        for route in ROUTES:
            for variant in route["variants"]:
                # Use partial ratio for better matching of longer phrases
                score = fuzz.partial_ratio(text_lower, variant.lower())
                print(f"--- Router comparing '{text}' with '{variant}': score {score}")
                if score > best_score:
                    best_score = score
                    best_module_name = route["module"]
                    
        print(f"--- Router best match: '{best_module_name}' with score {best_score}")
        
        if best_score >= ROUTER_THRESHOLD and best_module_name:
            module = self._load_module(best_module_name)
            return module, best_score
        return None, 0

    def handle(self, text):
        """
        Process the text through the appropriate module or fallback to ai.py.
        Returns the response string.
        """
        module, conf = self.route(text)
        if module:
            print(f"--- Router: routed to '{module.__name__}' with confidence {conf}")
            try:
                return module.handle(text)
            except Exception as e:
                print(f"--- Router: module '{module.__name__}' raised error: {e}")
                # Fallback to ai.py if module fails
                from ai import RuleBot
                bot = RuleBot()
                response, _ = bot.get_response(text)
                return response
        else:
            print(f"--- Router: no module matched, falling back to ai.py")
            from ai import RuleBot
            bot = RuleBot()
            response, _ = bot.get_response(text)
            return response

# Create a singleton instance for easy import
router = Router()