import os
import re
import json
import tarfile
import tempfile
import hashlib
import sqlite3
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Tuple

MODELS_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")
CACHE_ROOT = os.path.join(tempfile.gettempdir(), "alto_cache")
os.makedirs(CACHE_ROOT, exist_ok=True)

def safe_filename(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)

def find_model_dir(model_name: str):
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

def get_model_container_path(model_name: str):
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

def get_legacy_db_path(model_name: str):
    folder = find_model_dir(model_name)
    if not folder:
        return None
    safe = safe_filename(model_name)
    candidate = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.db")
    if os.path.isfile(candidate):
        return candidate
    for f in os.listdir(os.path.join(MODELS_BASE_DIR, folder)):
        if f.endswith('.db'):
            return os.path.join(MODELS_BASE_DIR, folder, f)
    return None

def read_manifest(container_path: str):
    try:
        with tarfile.open(container_path, 'r') as tar:
            member = tar.getmember('manifest.json')
            with tar.extractfile(member) as f:
                return json.load(f)
    except:
        return None

def get_db_alto_version(db_path: str) -> str | None:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.execute("SELECT alto_version FROM model_info")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None

class BaseLoader(ABC):
    @abstractmethod
    def get_version(self) -> str:
        pass

    @abstractmethod
    def get_connection(self, model_name: str) -> sqlite3.Connection:
        """Return a read‑only SQLite connection (may be used internally)."""
        pass

    # ----- Group matching (core AI logic) -----
    @abstractmethod
    def match_groups(self, text: str, topic_weights: Dict[str, int], threshold: int) -> Tuple[Optional[int], Optional[Dict], int]:
        """
        Find the best matching group for the input text.
        Returns (group_id, group_data, score) or (None, None, 0).
        group_data should contain at least:
            - id
            - group_name
            - topic
            - questions (list of str)
            - answers (list of str)
        """
        pass

    @abstractmethod
    def get_group_answers(self, group_id: int) -> List[str]:
        pass

    @abstractmethod
    def get_group_questions(self, group_id: int) -> List[str]:
        pass

    # ----- Follow‑up trees -----
    @abstractmethod
    def get_root_nodes(self, group_id: int) -> List[Dict]:
        """Return list of root nodes for a group's follow‑up tree (each node has id, branch_name, questions, answers)."""
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
    def match_nodes(self, text: str, nodes: List[Dict], threshold: int) -> Tuple[Optional[Dict], int]:
        """Find best matching node from a list of nodes."""
        pass

    # ----- Session state helpers -----
    @abstractmethod
    def get_topics(self) -> List[str]:
        pass

    @abstractmethod
    def get_sections(self) -> List[str]:
        pass

    @abstractmethod
    def get_variants(self) -> List[Dict]:
        pass

    # ----- Variant synonyms -----
    @abstractmethod
    def expand_synonyms(self, words: List[str]) -> set:
        pass