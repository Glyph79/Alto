import os
import configparser

DEFAULT_CONFIG = {
    'DEFAULT': {
        'port': '5001',
        'debug': 'True',
        'models_dir': 'models',
        'default_model': '',
        'recent_models': '',
    },
    'editor': {
        'auto_save': 'True',
        'theme': 'dark',
    },
    'cache': {
        'max_cached_models': '3',
    }
}

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "trainer_config.cfg")

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