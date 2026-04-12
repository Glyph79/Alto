# web/router/router.py
import sys
import os
import importlib
import re
import sqlite3
import json
from rapidfuzz import fuzz
from alto.config import config
from alto.core.dispatcher import Dispatcher

# Add resources directory to sys.path so modules inside resources/modules can be imported
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESOURCES_DIR = os.path.join(PROJECT_ROOT, 'resources')
if RESOURCES_DIR not in sys.path:
    sys.path.insert(0, RESOURCES_DIR)

ROUTER_THRESHOLD = config.getint('router', 'threshold')
MIN_WORD_SCORE = config.getint('router', 'min_word_score')
WORD_SCORER = fuzz.ratio

DB_PATH = os.path.join(PROJECT_ROOT, 'routing', 'router.db')

def normalize_word(word: str) -> str:
    return re.sub(r'[^\w\s]', '', word.lower())

class RouteEntry:
    __slots__ = ('module_name', 'variants', 'variant_words')
    def __init__(self, module_name, variants):
        self.module_name = module_name
        self.variants = [v.lower() for v in variants]
        self.variant_words = [
            [normalize_word(w) for w in v.split() if normalize_word(w)]
            for v in self.variants
        ]

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_name TEXT NOT NULL,
            variants TEXT NOT NULL
        )
    ''')
    cur = conn.execute('SELECT COUNT(*) FROM routes')
    if cur.fetchone()[0] == 0:
        default_variants = json.dumps([
            "what's the weather",
            "what is the weather",
            "forecast",
            "temperature",
            "rain",
            "weather today",
            "weather tomorrow"
        ])
        conn.execute('INSERT INTO routes (module_name, variants) VALUES (?, ?)',
                     ('weather', default_variants))
        conn.commit()
    conn.close()

def load_routes():
    if not os.path.exists(DB_PATH):
        init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute('SELECT module_name, variants FROM routes ORDER BY id')
    routes = []
    for row in cur:
        module_name = row[0]
        variants = json.loads(row[1])
        routes.append(RouteEntry(module_name, variants))
    conn.close()
    return routes

class Router:
    def __init__(self):
        self.modules = {}
        self.route_entries = load_routes()
        self.dispatcher = None

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
        return [normalize_word(w) for w in text.split() if normalize_word(w)]

    def _word_match_score(self, word, word_list):
        best = 0
        for w in word_list:
            score = WORD_SCORER(word, w)
            if score > best:
                best = score
                if best == 100:
                    return 100
        return best

    def _sentence_similarity(self, query_words, variant_words):
        if not query_words or not variant_words:
            return 0
        total = 0
        for qw in query_words:
            best = self._word_match_score(qw, variant_words)
            if best < MIN_WORD_SCORE:
                best = 0
            total += best
        avg = total / len(query_words)
        if len(query_words) < len(variant_words):
            avg *= (len(query_words) / len(variant_words))
        return avg

    def route(self, text: str, state: dict):
        if "current_module" in state:
            module = self._load_module(state["current_module"])
            if module:
                return module, 100

        text_lower = text.lower()
        query_words = self._get_query_words(text_lower)

        best_score = 0
        best_module_name = None

        for entry in self.route_entries:
            for variant, v_words in zip(entry.variants, entry.variant_words):
                score = self._sentence_similarity(query_words, v_words)
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
        module, conf = self.route(text, state)
        if module:
            print(f"--- Router: routed to '{module.__name__}' with confidence {conf:.1f}")
            try:
                return module.handle(text, state)
            except Exception as e:
                print(f"--- Router: module '{module.__name__}' raised error: {e}")
                return self._fallback_handle(text, state)
        else:
            print("--- Router: no module matched, falling back to bot")
            return self._fallback_handle(text, state)

    def _fallback_handle(self, text, state):
        if self.dispatcher is None:
            model_name = config.get('DEFAULT', 'default_model')
            self.dispatcher = Dispatcher(model_name)
        return self.dispatcher.process(text, state)

router = Router()