import os
import re
import datetime
from typing import Optional

MODELS_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")
os.makedirs(MODELS_BASE_DIR, exist_ok=True)

def safe_filename(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)

def timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")

def find_model_dir(model_name: str) -> Optional[str]:
    safe = safe_filename(model_name)
    if not os.path.exists(MODELS_BASE_DIR):
        return None
    for entry in os.listdir(MODELS_BASE_DIR):
        full_path = os.path.join(MODELS_BASE_DIR, entry)
        if not os.path.isdir(full_path):
            continue
        if entry.endswith('_' + safe):
            return entry
    return None

def ensure_model_dir(model_name: str) -> str:
    safe = safe_filename(model_name)
    base = f"{timestamp()}_{safe}"
    candidate = base
    counter = 1
    while os.path.exists(os.path.join(MODELS_BASE_DIR, candidate)):
        candidate = f"{base}_{counter}"
        counter += 1
    full_path = os.path.join(MODELS_BASE_DIR, candidate)
    os.makedirs(full_path, exist_ok=True)
    return candidate

def get_model_db_path(model_name: str) -> Optional[str]:
    folder = find_model_dir(model_name)
    if not folder:
        return None
    safe = safe_filename(model_name)
    return os.path.join(MODELS_BASE_DIR, folder, f"{safe}.db")