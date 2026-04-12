# alto/config.py
import os
import configparser

DEFAULT_CONFIG = {
    'DEFAULT': {
        'default_model': 'Alto',
        'models_dir': 'resources/models',
        'sessions_dir': 'resources/sessions',   # <-- sessions now in resources/
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
    },
    'ai': {
        'max_topics': '3',
        'topic_decay': '5',
        'topic_boost_max': '20',
        'scan_interval': '5',
        'threshold': '70',
        'debug': 'False',
    }
}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_DIR = os.path.join(PROJECT_ROOT, 'resources')
CONFIG_PATH = os.path.join(RESOURCES_DIR, 'backend_config.cfg')

def ensure_resources_dir():
    os.makedirs(RESOURCES_DIR, exist_ok=True)

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