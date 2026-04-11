import sqlite3
import time
import os
import shutil
import tempfile
import datetime
from collections import OrderedDict
from typing import List, Dict, Optional, Any

from .constants import ALTO_VERSION
from .tables import init_model_db, create_empty_schema, get_model_info
from .groups import (
    get_group_summaries, get_group_summaries_with_counts,
    get_group_by_id, insert_group, update_group, delete_group
)
from .sections import get_sections_list, add_section, rename_section, delete_section
from .topics import get_topics_list, add_topic, rename_topic, delete_topic, get_topic_groups
from .variants import get_variants, add_variant, update_variant, delete_variant
from .fallbacks import (
    get_fallbacks, get_fallback_by_id, create_fallback, update_fallback,
    delete_fallback, get_groups_by_fallback, get_nodes_by_fallback
)
from .helpers import _get_or_create_question_id
from .blob_utils import store_blob, release_blob, get_blob_data
from ..utils.msgpack_helpers import pack_array, unpack_array
from ..utils.file_helpers import (
    get_model_db_path, find_model_dir, safe_filename, MODELS_BASE_DIR,
    get_model_container_path, get_model_temp_dir, pack_model, unpack_model, read_manifest
)

class Model:
    def __init__(self, name: str):
        self.name = name
        self.container_path = get_model_container_path(name)
        self.temp_dir = get_model_temp_dir(name)
        self.db_path = None

        if self.container_path:
            self.db_path, manifest = unpack_model(self.container_path, self.temp_dir)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blob_store'")
            if cursor.fetchone() is None:
                conn.close()
                raise RuntimeError(f"Model '{name}' uses an old schema that is no longer supported. Please re-import the original .db file.")
            else:
                conn.close()
        else:
            legacy_db_path = get_model_db_path(name)
            if legacy_db_path and os.path.isfile(legacy_db_path):
                self._migrate_legacy_folder(legacy_db_path)
                self.container_path = get_model_container_path(name)
                self.db_path, manifest = unpack_model(self.container_path, self.temp_dir)
            else:
                raise FileNotFoundError(f"Model '{name}' not found")

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA cache_size = -5000")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA mmap_size = 30000000000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row

        self._group_summaries = None
        self.last_used = time.time()

    def _migrate_legacy_folder(self, legacy_db_path: str):
        """Convert a legacy .db file (0.1a) to the new optimised schema."""
        temp_conn = sqlite3.connect(legacy_db_path)
        temp_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        temp_conn.close()

        new_db_path = os.path.join(self.temp_dir, "new_database.db")
        new_conn = sqlite3.connect(new_db_path)
        create_empty_schema(new_conn)

        new_conn.execute(f"ATTACH DATABASE '{legacy_db_path}' AS old")

        # Copy sections, topics, variants
        for table in ['sections', 'topics', 'variant_groups', 'variant_words']:
            new_conn.execute(f"INSERT INTO {table} SELECT * FROM old.{table}")

        now_iso = datetime.datetime.now().isoformat()

        # Migrate groups
        cur = new_conn.execute("SELECT id, group_name, topic_id, section_id, questions_blob, answers_blob FROM old.groups")
        for row in cur:
            gid, gname, tid, sid, q_blob, a_blob = row
            questions = unpack_array(q_blob) if q_blob else []
            answers = unpack_array(a_blob) if a_blob else []
            q_raw = pack_array(questions)
            a_raw = pack_array(answers)
            q_id = store_blob(new_conn, q_raw, normalise=True)
            a_id = store_blob(new_conn, a_raw, normalise=False)
            new_conn.execute(
                """INSERT INTO groups
                   (id, group_name, topic_id, section_id, fallback_id, questions_blob_id, answers_blob_id, answer_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (gid, gname, tid, sid, None, q_id, a_id, len(answers), now_iso, now_iso)
            )
            for idx, q in enumerate(questions):
                qid = _get_or_create_question_id(new_conn, q)
                new_conn.execute(
                    "INSERT INTO group_questions (group_id, question_id, sort_order) VALUES (?, ?, ?)",
                    (gid, qid, idx)
                )

        # Migrate followup_nodes
        cur = new_conn.execute("SELECT id, group_id, parent_id, branch_name, questions_blob, answers_blob FROM old.followup_nodes")
        for row in cur:
            nid, gid, pid, bname, q_blob, a_blob = row
            questions = unpack_array(q_blob) if q_blob else []
            answers = unpack_array(a_blob) if a_blob else []
            q_raw = pack_array(questions)
            a_raw = pack_array(answers)
            q_id = store_blob(new_conn, q_raw, normalise=True)
            a_id = store_blob(new_conn, a_raw, normalise=False)
            new_conn.execute(
                "INSERT INTO followup_nodes (id, group_id, parent_id, branch_name, questions_blob_id, answers_blob_id, fallback_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nid, gid, pid, bname, q_id, a_id, None)
            )

        # Model info
        cur = new_conn.execute("SELECT name, description, author, version, alto_version, created_at, updated_at FROM old.model_info")
        row = cur.fetchone()
        if row:
            name, desc, author, version, alto_ver, created, updated = row
        else:
            name, desc, author, version, alto_ver = self.name, "", "", "1.0.0", "0.1a"
            created = updated = now_iso
        new_conn.execute(
            "INSERT INTO model_info (name, description, author, version, alto_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, desc, author, version, alto_ver, created, updated)
        )

        new_conn.execute("DETACH old")
        new_conn.commit()
        new_conn.close()

        # Pack the new database into a .rbm
        folder = find_model_dir(self.name)
        safe = safe_filename(self.name)
        container_path = os.path.join(MODELS_BASE_DIR, folder, f"{safe}.rbm")
        fd, tmp_path = tempfile.mkstemp(suffix='.rbm', dir=os.path.dirname(container_path))
        os.close(fd)
        try:
            pack_model(new_db_path, get_model_info(sqlite3.connect(new_db_path)), tmp_path)
            os.replace(tmp_path, container_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        for ext in ['.db', '.db-wal', '.db-shm']:
            f = legacy_db_path.replace('.db', ext) if ext != '.db' else legacy_db_path
            if os.path.exists(f):
                os.remove(f)

    def close_and_repack(self):
        if self.conn is None:
            return
        manifest = get_model_info(self.conn)
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.close()
        self.conn = None
        fd, tmp_path = tempfile.mkstemp(suffix='.rbm', dir=os.path.dirname(self.container_path))
        os.close(fd)
        try:
            pack_model(self.db_path, manifest, tmp_path)
            os.replace(tmp_path, self.container_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def close_without_repack(self):
        if self.conn is None:
            return
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.close()
        self.conn = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _load_group_summaries(self):
        self._group_summaries = get_group_summaries(self.conn)

    def get_group_summaries(self) -> List[Dict]:
        self.last_used = time.time()
        if self._group_summaries is None:
            self._load_group_summaries()
        return self._group_summaries

    def get_group_summaries_with_counts(self) -> List[Dict]:
        self.last_used = time.time()
        return get_group_summaries_with_counts(self.conn)

    def get_sections(self) -> List[str]:
        self.last_used = time.time()
        return get_sections_list(self.conn)

    def get_topics(self) -> List[str]:
        self.last_used = time.time()
        return get_topics_list(self.conn)

    def get_group_by_id(self, group_id: int, include_followups: bool = False) -> Dict:
        self.last_used = time.time()
        return get_group_by_id(self.conn, group_id, include_followups)

    def insert_group(self, group_dict: Dict) -> int:
        self.last_used = time.time()
        group_id = insert_group(self.conn, self.name, group_dict)
        self._group_summaries = None
        return group_id

    def update_group(self, group_id: int, group_dict: Dict):
        self.last_used = time.time()
        update_group(self.conn, group_id, group_dict)
        self._group_summaries = None

    def delete_group(self, group_id: int):
        self.last_used = time.time()
        delete_group(self.conn, group_id)
        self._group_summaries = None

    def add_section(self, name: str) -> int:
        self.last_used = time.time()
        return add_section(self.conn, name)

    def rename_section(self, old_name: str, new_name: str):
        self.last_used = time.time()
        rename_section(self.conn, old_name, new_name)

    def delete_section(self, name: str, action: str = "uncategorized", target: Optional[str] = None):
        self.last_used = time.time()
        delete_section(self.conn, name, action, target)

    def add_topic(self, name: str, section_name: Optional[str] = None) -> int:
        self.last_used = time.time()
        return add_topic(self.conn, name, section_name)

    def rename_topic(self, old_name: str, new_name: str):
        self.last_used = time.time()
        rename_topic(self.conn, old_name, new_name)

    def delete_topic(self, name: str, action: str = "reassign", target: Optional[str] = None):
        self.last_used = time.time()
        delete_topic(self.conn, name, action, target)

    def get_topic_groups(self, topic_name: str) -> List[Dict]:
        self.last_used = time.time()
        return get_topic_groups(self.conn, topic_name)

    def get_variants(self) -> List[Dict]:
        self.last_used = time.time()
        return get_variants(self.conn)

    def add_variant(self, name: str, section_name: Optional[str], words: List[str]) -> int:
        self.last_used = time.time()
        return add_variant(self.conn, name, section_name, words)

    def update_variant(self, variant_id: int, name: str, section_name: Optional[str], words: List[str]):
        self.last_used = time.time()
        update_variant(self.conn, variant_id, name, section_name, words)

    def delete_variant(self, variant_id: int):
        self.last_used = time.time()
        delete_variant(self.conn, variant_id)

    def get_fallbacks(self) -> List[Dict]:
        self.last_used = time.time()
        return get_fallbacks(self.conn)

    def get_fallback_by_id(self, fallback_id: int) -> Dict:
        self.last_used = time.time()
        return get_fallback_by_id(self.conn, fallback_id)

    def create_fallback(self, name: str, description: str, answers: List[str]) -> int:
        self.last_used = time.time()
        return create_fallback(self.conn, name, description, answers)

    def update_fallback(self, fallback_id: int, name: str, description: str, answers: List[str]):
        self.last_used = time.time()
        update_fallback(self.conn, fallback_id, name, description, answers)

    def delete_fallback(self, fallback_id: int):
        self.last_used = time.time()
        delete_fallback(self.conn, fallback_id)

    def get_groups_by_fallback(self, fallback_id: int) -> List[Dict]:
        self.last_used = time.time()
        return get_groups_by_fallback(self.conn, fallback_id)

    def get_nodes_by_fallback(self, fallback_id: int) -> List[Dict]:
        self.last_used = time.time()
        return get_nodes_by_fallback(self.conn, fallback_id)


_model_cache: OrderedDict[str, Model] = OrderedDict()
MAX_CACHED_MODELS = 3

def get_model(name: str) -> Model:
    global _model_cache
    if name in _model_cache:
        model = _model_cache.pop(name)
        model.last_used = time.time()
        _model_cache[name] = model
        return model
    else:
        model = Model(name)
        if len(_model_cache) >= MAX_CACHED_MODELS:
            oldest_name, oldest_model = _model_cache.popitem(last=False)
            oldest_model.close_and_repack()
        _model_cache[name] = model
        return model

def close_all_models():
    for model in _model_cache.values():
        model.close_and_repack()
    _model_cache.clear()