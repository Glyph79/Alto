import os
import configparser

DEFAULT_CONFIG = {
    'DEFAULT': {
        'port': '5001',
        'debug': 'True',
        'models_dir': 'models',
        'default_model': '',
        'recent_models': '',
        'serve_webui': 'True',
    },
    'converter': {
        'batch_size': '100',
        # 'create_missing' removed – always enabled in converter
    },
    'editor': {
        'auto_save': 'True',
        'theme': 'dark',
    },
    'cache': {
        'max_cached_models': '3',
    }
}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_DIR = os.path.join(PROJECT_ROOT, 'resources')
CONFIG_PATH = os.path.join(RESOURCES_DIR, 'trainer_config.cfg')

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