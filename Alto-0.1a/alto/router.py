import importlib
import re
from fuzzywuzzy import fuzz

# ========== CONFIGURATION ==========
ROUTER_THRESHOLD = 70               # Minimum overall sentence similarity
WORD_SCORER = fuzz.ratio             # Scorer for individual word matching
MIN_WORD_SCORE = 80                   # Words scoring below this are treated as 0
# ====================================

def normalize_word(word: str) -> str:
    """Strip punctuation and lowercase."""
    return re.sub(r'[^\w\s]', '', word.lower())

class RouteEntry:
    __slots__ = ('module_name', 'variants', 'variant_words')
    def __init__(self, module_name, variants):
        self.module_name = module_name
        self.variants = [v.lower() for v in variants]
        # Pre‑compute list of words for each variant (keep all words, no length filter)
        self.variant_words = [
            [normalize_word(w) for w in v.split() if normalize_word(w)]
            for v in self.variants
        ]

ROUTES = [
    RouteEntry("weather", [
        "what's the weather",
        "what is the weather",
        "forecast",
        "temperature",
        "rain",
        "weather today",
        "weather tomorrow"
    ]),
    # Add more routes here
]

class Router:
    def __init__(self):
        self.modules = {}               # cache imported modules
        self.route_entries = ROUTES

    def _load_module(self, module_name):
        if module_name in self.modules:
            return self.modules[module_name]
        try:
            module = importlib.import_module(f"modules.{module_name}")
            self.modules[module_name] = module
            return module
        except ImportError as e:
            print(f"--- Router: could not load module '{module_name}': {e}")
            return None

    def _get_query_words(self, text: str):
        """Normalize and split query into words (keep all, even short ones)."""
        return [normalize_word(w) for w in text.split() if normalize_word(w)]

    def _word_match_score(self, word, word_list):
        """Best fuzzy score for a single word against a list of words."""
        best = 0
        for w in word_list:
            score = WORD_SCORER(word, w)
            if score > best:
                best = score
                if best == 100:
                    return 100
        return best

    def _sentence_similarity(self, query_words, variant_words):
        """
        Compute similarity between query and a variant.
        - For each query word, find best match score in variant words.
        - If a word's best score is below MIN_WORD_SCORE, treat it as 0.
        - Average the (possibly zeroed) scores.
        - Apply length penalty if query has fewer words than variant.
        """
        if not query_words or not variant_words:
            return 0

        total = 0
        for qw in query_words:
            best = self._word_match_score(qw, variant_words)
            if best < MIN_WORD_SCORE:
                best = 0
            total += best

        avg = total / len(query_words)

        # Length penalty: if query has fewer words, scale down proportionally
        if len(query_words) < len(variant_words):
            avg *= (len(query_words) / len(variant_words))

        return avg

    def route(self, text: str, state: dict):
        """Return (module, confidence) for this message, respecting active module."""
        # 1. Active module override
        if "current_module" in state:
            module = self._load_module(state["current_module"])
            if module:
                return module, 100

        # 2. Preprocess query
        text_lower = text.lower()
        query_words = self._get_query_words(text_lower)

        best_score = 0
        best_module_name = None

        # 3. Evaluate all routes, keep the best match
        for entry in self.route_entries:
            for variant, v_words in zip(entry.variants, entry.variant_words):
                score = self._sentence_similarity(query_words, v_words)

                # Exact match boost (ensures perfect queries get high score)
                if text_lower == variant:
                    score = max(score, 90)

                if score > best_score:
                    best_score = score
                    best_module_name = entry.module_name

        print(f"--- Router best match: '{best_module_name}' with score {best_score:.1f}")

        if best_score >= ROUTER_THRESHOLD and best_module_name:
            return self._load_module(best_module_name), best_score
        return None, 0

    def handle(self, text: str, state: dict):
        """Main entry point – route and call module/fallback."""
        module, conf = self.route(text, state)
        if module:
            print(f"--- Router: routed to '{module.__name__}' with confidence {conf:.1f}")
            try:
                return module.handle(text, state)
            except Exception as e:
                print(f"--- Router: module '{module.__name__}' raised error: {e}")
                from ai import handle as fallback_handle
                return fallback_handle(text, state)
        else:
            print("--- Router: no module matched, falling back to ai.py")
            from ai import handle as fallback_handle
            return fallback_handle(text, state)

# Singleton
router = Router()