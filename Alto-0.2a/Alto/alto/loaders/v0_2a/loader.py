import os
import hashlib
import tarfile
import sqlite3
from ..base import BaseLoader, MODELS_BASE_DIR, CACHE_ROOT, get_model_container_path

class LoaderV0_2a(BaseLoader):
    VERSION = "0.2a"

    def get_version(self) -> str:
        return self.VERSION

    def get_connection(self, model_name: str) -> sqlite3.Connection:
        container_path = get_model_container_path(model_name)
        if not container_path or not os.path.isfile(container_path):
            raise FileNotFoundError(f"Model '{model_name}' not found (.rbm container missing)")

        mtime = os.path.getmtime(container_path)
        key = hashlib.md5(f"{model_name}_{mtime}".encode()).hexdigest()[:16]
        cache_dir = os.path.join(CACHE_ROOT, model_name, key)
        db_path = os.path.join(cache_dir, "database.db")

        if not (os.path.isfile(db_path) and os.path.getmtime(db_path) >= mtime):
            os.makedirs(cache_dir, exist_ok=True)
            with tarfile.open(container_path, 'r') as tar:
                tar.extractall(cache_dir)
            if not os.path.isfile(db_path):
                raise RuntimeError(f"Extraction failed: {db_path} missing")

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        conn.execute("PRAGMA query_only = 1")
        conn.row_factory = sqlite3.Row
        return conn