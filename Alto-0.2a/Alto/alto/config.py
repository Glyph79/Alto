import os
import configparser

DEFAULT_CONFIG = {
    'DEFAULT': {
        'default_model': 'Alto',
        'models_dir': 'models',
        'sessions_dir': 'sessions',
        'fallback': "I'm sorry, I didn't understand that.",
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
        'cleanup_interval': '1',
    },
    'ai': {
        'max_topics': '3',
        'topic_decay': '5',
        'topic_boost_max': '20',
        'scan_interval': '5',
        'threshold': '70',
    }
}

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "alto_config.cfg")

def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists(CONFIG_PATH):
        # Create new config with defaults
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
        # Ensure all default sections and options exist
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
        save_config(config)
    return config

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)

config = load_config()