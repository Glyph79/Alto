# alto/config.py
import os
import configparser

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_DIR = os.path.join(PROJECT_ROOT, 'resources')
CONFIG_PATH = os.path.join(RESOURCES_DIR, 'alto_config.cfg')

MODELS_DIR = os.path.join(RESOURCES_DIR, 'models')
SESSIONS_DIR = os.path.join(RESOURCES_DIR, 'sessions')
USERS_DIR = os.path.join(RESOURCES_DIR, 'users')

DEFAULT_CONFIG = {
    'DEFAULT': {
        'default_model': 'Alto',
        'fallback': "I'm sorry, I didn't understand that.",
        'serve_webui': 'True',
    },
    'stream': {
        'by_char': 'True',
        'delay': '0.005',
    },
    'router': {
        'threshold': '70',
        'min_word_score': '80',
    },
    'session': {
        'hot_timeout': '5',
        'cold_timeout': '10',
        'cleanup_interval': '5',
        'max_active_trees': '3',
        'navigation_mode': 'strict',
        'max_hot_sessions': '100',       # NEW: limit hot sessions
    },
    'ai': {
        'max_topics': '3',
        'topic_decay': '5',
        'topic_boost_max': '20',
        'scan_interval': '5',
        'threshold': '70',
        'debug': 'False',
        'max_candidate_groups': '50',
        'ram_only_mode': 'False',
        'enable_jit_cache': 'True',
        'max_typo_cache': '1000',
        'max_exact_cache': '500',
        'jit_ram_only_mode': 'False',
        'max_workers': '8',                     # NEW: thread pool size
        'cache_max_groups': '3000',             # NEW: per‑type cache limits
        'cache_max_nodes': '3000',
        'cache_max_fallbacks': '1000',
        'cache_group_linger_seconds': '30',
    },
    'admin': {
        'password': '7134',
    }
}

def ensure_resources_dir():
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    os.makedirs(USERS_DIR, exist_ok=True)

def load_config():
    ensure_resources_dir()
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_PATH):
        for section, options in DEFAULT_CONFIG.items():
            if section == 'DEFAULT':
                for key, val in options.items():
                    config.set('DEFAULT', key, val)
            else:
                config.add_section(section)
                for key, val in options.items():
                    config.set(section, key, val)
        save_config(config)
    else:
        config.read(CONFIG_PATH)
        for section, options in DEFAULT_CONFIG.items():
            if section == 'DEFAULT':
                for key, val in options.items():
                    if not config.has_option('DEFAULT', key):
                        config.set('DEFAULT', key, val)
            else:
                if not config.has_section(section):
                    config.add_section(section)
                for key, val in options.items():
                    if not config.has_option(section, key):
                        config.set(section, key, val)
    return config

def save_config(config):
    ensure_resources_dir()
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)

config = load_config()