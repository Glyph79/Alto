import os
import re
import datetime
import json
import tarfile
import tempfile
import hashlib
import sqlite3
import io
from typing import Optional, Dict, Tuple

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

def pack_model(db_path: str, manifest: Dict, output_path: str) -> None:
    with tarfile.open(output_path, 'w') as tar:
        tar.add(db_path, arcname='database.db')
        manifest_bytes = json.dumps(manifest, indent=2).encode('utf-8')
        manifest_info = tarfile.TarInfo(name='manifest.json')
        manifest_info.size = len(manifest_bytes)
        tar.addfile(manifest_info, fileobj=io.BytesIO(manifest_bytes))

def unpack_model(container_path: str, dest_dir: str) -> Tuple[str, Dict]:
    with tarfile.open(container_path, 'r') as tar:
        tar.extractall(dest_dir)
    db_path = os.path.join(dest_dir, 'database.db')
    manifest_path = os.path.join(dest_dir, 'manifest.json')
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    return db_path, manifest

def read_manifest(container_path: str) -> Optional[Dict]:
    try:
        with tarfile.open(container_path, 'r') as tar:
            member = tar.getmember('manifest.json')
            with tar.extractfile(member) as f:
                return json.load(f)
    except (KeyError, tarfile.TarError, json.JSONDecodeError):
        return None

def get_model_container_path(model_name: str) -> Optional[str]:
    folder = find_model_dir(model_name)
    if not folder:
        return None
    safe = safe_filename(model_name)
    candidate = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.rbm")
    if os.path.isfile(candidate):
        return candidate
    for f in os.listdir(os.path.join(MODELS_BASE_DIR, folder)):
        if f.endswith('.rbm'):
            return os.path.join(MODELS_BASE_DIR, folder, f)
    return None

def get_model_temp_dir(model_name: str) -> str:
    safe = safe_filename(model_name)
    hash_suffix = hashlib.md5(model_name.encode()).hexdigest()[:8]
    temp_root = os.path.join(tempfile.gettempdir(), 'alto_trainer_models')
    os.makedirs(temp_root, exist_ok=True)
    temp_dir = os.path.join(temp_root, f"{safe}_{hash_suffix}")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir