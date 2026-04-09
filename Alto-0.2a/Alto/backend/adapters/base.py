# Alto/backend/adapters/base.py
import os
import re
import json
import tarfile
import tempfile
import hashlib
import sqlite3
import importlib.util
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Set, Type

# -------- Path utilities --------
MODELS_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")
CACHE_ROOT = os.path.join(tempfile.gettempdir(), "alto_cache")
os.makedirs(CACHE_ROOT, exist_ok=True)

def safe_filename(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)

def find_model_dir(model_name: str) -> Optional[str]:
    safe = safe_filename(model_name)
    if not os.path.exists(MODELS_BASE_DIR):
        return None
    for entry in os.listdir(MODELS_BASE_DIR):
        full_path = os.path.join(MODELS_BASE_DIR, entry)
        if not os.path.isdir(full_path):
            continue
        if entry.endswith('_' + safe) or safe in entry:
            return entry
    return None

def get_model_container_path(model_name: str) -> Optional[str]:
    safe = safe_filename(model_name)
    flat_path = os.path.join(MODELS_BASE_DIR, f"{safe}.rbm")
    if os.path.isfile(flat_path):
        return flat_path
    folder = find_model_dir(model_name)
    if folder:
        candidate = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.rbm")
        if os.path.isfile(candidate):
            return candidate
        folder_path = os.path.join(MODELS_BASE_DIR, folder)
        for f in os.listdir(folder_path):
            if f.endswith('.rbm'):
                return os.path.join(folder_path, f)
    return None

def get_legacy_db_path(model_name: str) -> Optional[str]:
    safe = safe_filename(model_name)
    flat_path = os.path.join(MODELS_BASE_DIR, f"{safe}.db")
    if os.path.isfile(flat_path):
        return flat_path
    folder = find_model_dir(model_name)
    if folder:
        candidate = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.db")
        if os.path.isfile(candidate):
            return candidate
        folder_path = os.path.join(MODELS_BASE_DIR, folder)
        for f in os.listdir(folder_path):
            if f.endswith('.db'):
                return os.path.join(folder_path, f)
    return None

def read_manifest(container_path: str):
    try:
        with tarfile.open(container_path, 'r') as tar:
            member = tar.getmember('manifest.json')
            with tar.extractfile(member) as f:
                return json.load(f)
    except:
        return None

def get_db_alto_version(db_path: str) -> Optional[str]:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.execute("SELECT alto_version FROM model_info")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None

# -------- Abstract Adapter --------
class BaseAdapter(ABC):
    @abstractmethod
    def get_version(self) -> str:
        pass

    @abstractmethod
    def get_connection(self, model_name: str) -> sqlite3.Connection:
        pass

    @abstractmethod
    def get_group_questions(self, group_id: int) -> List[str]:
        pass

    @abstractmethod
    def get_group_answers(self, group_id: int) -> List[str]:
        pass

    @abstractmethod
    def get_group_data(self, group_id: int) -> Dict:
        pass

    @abstractmethod
    def get_root_nodes(self, group_id: int) -> List[Dict]:
        pass

    @abstractmethod
    def get_node_children(self, node_id: int) -> List[Dict]:
        pass

    @abstractmethod
    def get_node_questions(self, node_id: int) -> List[str]:
        pass

    @abstractmethod
    def get_node_answers(self, node_id: int) -> List[str]:
        pass

    @abstractmethod
    def get_topics(self) -> List[str]:
        pass

    @abstractmethod
    def get_sections(self) -> List[str]:
        pass

    @abstractmethod
    def get_variants(self) -> List[Dict]:
        pass

    @abstractmethod
    def expand_synonyms(self, words: List[str]) -> Set[str]:
        pass


# -------- Automatic adapter discovery (static mapping from filenames) --------
def _discover_adapters() -> Dict[str, Type[BaseAdapter]]:
    """Scan the 'versions' folder and return a dict version -> adapter class.
    Expects files named v{version}.py (e.g., v0_1a.py) containing a class named
    AdapterV{version} (e.g., AdapterV0_1a). The version string is extracted by
    removing the 'AdapterV' prefix and converting underscores back to dots.
    """
    adapters = {}
    versions_dir = os.path.join(os.path.dirname(__file__), 'versions')
    if not os.path.isdir(versions_dir):
        return adapters

    for filename in os.listdir(versions_dir):
        if not filename.endswith('.py') or filename == '__init__.py':
            continue
        # Extract version from filename: v0_1a.py -> "0_1a"
        if not filename.startswith('v'):
            continue
        version_part = filename[1:-3]  # remove 'v' and '.py'
        # Convert underscores to dots for version string: "0_1a" -> "0.1a"
        version = version_part.replace('_', '.')
        module_name = f"backend.adapters.versions.{filename[:-3]}"
        try:
            spec = importlib.util.spec_from_file_location(
                module_name,
                os.path.join(versions_dir, filename)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # Find the adapter class (should be named AdapterV{version_part})
            class_name = f"AdapterV{version_part}"
            adapter_class = getattr(module, class_name, None)
            if adapter_class and issubclass(adapter_class, BaseAdapter):
                adapters[version] = adapter_class
        except Exception as e:
            print(f"Warning: Could not load adapter {filename}: {e}")
    return adapters

_ADAPTER_MAP = _discover_adapters()

def get_adapter(model_name: str) -> BaseAdapter:
    """Return the appropriate adapter for the given model."""
    container_path = get_model_container_path(model_name)
    if container_path and os.path.isfile(container_path):
        manifest = read_manifest(container_path)
        if manifest:
            version = manifest.get("alto_version")
            if version in _ADAPTER_MAP:
                return _ADAPTER_MAP[version]()
    legacy_path = get_legacy_db_path(model_name)
    if legacy_path and os.path.isfile(legacy_path):
        version = get_db_alto_version(legacy_path)
        if version in _ADAPTER_MAP:
            return _ADAPTER_MAP[version]()
    raise FileNotFoundError(f"Model '{model_name}' not found or version unsupported")