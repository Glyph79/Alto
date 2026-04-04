import os
import sys
import hashlib
import sqlite3
from ..base import BaseLoader, CACHE_ROOT, get_legacy_db_path, get_db_alto_version

class LoaderV0_1a(BaseLoader):
    VERSION = "0.1a"

    def get_version(self) -> str:
        return self.VERSION

    def get_connection(self, model_name: str) -> sqlite3.Connection:
        legacy_path = get_legacy_db_path(model_name)
        if not legacy_path or not os.path.isfile(legacy_path):
            raise FileNotFoundError(f"Model '{model_name}' not found (legacy .db missing)")

        mtime = os.path.getmtime(legacy_path)
        key = hashlib.md5(f"{model_name}_{mtime}".encode()).hexdigest()[:16]
        cache_dir = os.path.join(CACHE_ROOT, model_name, "v0_1a", key)
        os.makedirs(cache_dir, exist_ok=True)
        temp_db_path = os.path.join(cache_dir, "compat.db")

        if os.path.isfile(temp_db_path) and os.path.getmtime(temp_db_path) >= mtime:
            conn = sqlite3.connect(f"file:{temp_db_path}?mode=ro", uri=True, check_same_thread=False)
            conn.execute("PRAGMA query_only = 1")
            conn.row_factory = sqlite3.Row
            return conn

        # Create view‑based compatibility database
        conn = sqlite3.connect(temp_db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"ATTACH DATABASE '{legacy_path}' AS original")

        # Groups view with computed question_count and answer_count
        conn.execute("""
            CREATE VIEW groups AS
            SELECT
                g.id,
                g.group_name,
                g.topic_id,
                g.section_id,
                g.questions_blob,
                g.answers_blob,
                (SELECT COUNT(*) FROM original.questions_fts WHERE group_id = g.id) AS question_count,
                (SELECT json_array_length(g.answers_blob)) AS answer_count
            FROM original.groups g
        """)

        # Sections view
        conn.execute("CREATE VIEW sections AS SELECT * FROM original.sections")
        # Topics view
        conn.execute("CREATE VIEW topics AS SELECT * FROM original.topics")
        # Empty variant views (0.1a didn't have them)
        conn.execute("CREATE VIEW variant_groups AS SELECT id, name, section_id, created_at FROM original.variant_groups WHERE 0")
        conn.execute("CREATE VIEW variant_words AS SELECT word, group_id FROM original.variant_words WHERE 0")
        # Followup nodes view
        conn.execute("CREATE VIEW followup_nodes AS SELECT * FROM original.followup_nodes")
        # FTS view (exposes the original FTS table)
        conn.execute("CREATE VIEW questions_fts AS SELECT group_id, question FROM original.questions_fts")

        conn.commit()
        conn.close()

        conn = sqlite3.connect(f"file:{temp_db_path}?mode=ro", uri=True, check_same_thread=False)
        conn.execute("PRAGMA query_only = 1")
        conn.row_factory = sqlite3.Row
        return conn