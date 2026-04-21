# web/plugins/indexer.py
import os
import re
import sqlite3
import hashlib
from typing import List, Tuple, Optional
from rapidfuzz import fuzz

class PluginIndexer:
    def __init__(self, plugins_dir: str):
        self.plugins_dir = plugins_dir
        self.db_path = os.path.join(plugins_dir, 'plugin_index.db')
        self._last_build_mtime = self._get_last_build_mtime()
        self._init_db()
        # Cache for fuzzy matching (refresh on rebuild)
        self._cached_triggers = None

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plugins (
                name TEXT PRIMARY KEY,
                file_mtime REAL,
                file_hash TEXT
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS triggers_fts USING fts5(
                trigger_text, plugin_name, content=triggers
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS triggers (
                id INTEGER PRIMARY KEY,
                trigger_text TEXT UNIQUE,
                plugin_name TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _get_last_build_mtime(self) -> float:
        if not os.path.exists(self.db_path):
            return 0
        return os.path.getmtime(self.db_path)

    def _get_plugin_hash(self, path: str) -> str:
        with open(path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def _extract_triggers_from_plug(self, path: str) -> List[str]:
        triggers = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('root '):
                    parts = line[5:].rstrip(':').split(' as ')
                    trigger = parts[0].strip()
                    triggers.append(trigger)
                elif line.startswith('define input '):
                    match = re.findall(r'"([^"]*)"', line)
                    triggers.extend(match)
        return triggers

    def rebuild_if_changed(self):
        current_mtime = 0
        any_changed = False
        for fname in os.listdir(self.plugins_dir):
            if not fname.endswith('.plug'):
                continue
            path = os.path.join(self.plugins_dir, fname)
            mtime = os.path.getmtime(path)
            current_mtime = max(current_mtime, mtime)
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute("SELECT file_mtime, file_hash FROM plugins WHERE name = ?", (fname[:-5],))
            row = cur.fetchone()
            conn.close()
            if not row or row[0] < mtime or row[1] != self._get_plugin_hash(path):
                any_changed = True
                break
        if any_changed or current_mtime > self._get_last_build_mtime():
            self._rebuild_full()

    def _rebuild_full(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM plugins")
        conn.execute("DELETE FROM triggers")
        conn.execute("DELETE FROM triggers_fts")
        conn.commit()

        for fname in os.listdir(self.plugins_dir):
            if not fname.endswith('.plug'):
                continue
            plugin_name = fname[:-5]
            path = os.path.join(self.plugins_dir, fname)
            mtime = os.path.getmtime(path)
            file_hash = self._get_plugin_hash(path)
            triggers = self._extract_triggers_from_plug(path)

            conn.execute(
                "INSERT INTO plugins (name, file_mtime, file_hash) VALUES (?, ?, ?)",
                (plugin_name, mtime, file_hash)
            )
            for trigger in triggers:
                conn.execute(
                    "INSERT INTO triggers (trigger_text, plugin_name) VALUES (?, ?)",
                    (trigger.lower(), plugin_name)
                )
        conn.execute("""
            INSERT INTO triggers_fts(rowid, trigger_text, plugin_name)
            SELECT id, trigger_text, plugin_name FROM triggers
        """)
        conn.commit()
        conn.close()
        os.utime(self.db_path, None)
        # Clear cache so fuzzy matching reloads triggers
        self._cached_triggers = None

    def force_rebuild(self):
        self._rebuild_full()

    def match(self, text: str) -> Optional[Tuple[str, float]]:
        text_lower = text.lower().strip()
        conn = sqlite3.connect(self.db_path)
        # 1. Exact match (fast path)
        cur = conn.execute(
            "SELECT plugin_name, trigger_text FROM triggers WHERE trigger_text = ? LIMIT 1",
            (text_lower,)
        )
        exact = cur.fetchone()
        conn.close()
        if exact:
            return exact[0], 100.0

        # 2. Fuzzy match using cached triggers
        if self._cached_triggers is None:
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute("SELECT plugin_name, trigger_text FROM triggers")
            self._cached_triggers = cur.fetchall()
            conn.close()

        best_plugin = None
        best_score = 0
        for plugin_name, trigger in self._cached_triggers:
            # token_set_ratio handles word reordering and partial matches
            score = fuzz.token_set_ratio(text_lower, trigger.lower())
            if score > best_score:
                best_score = score
                best_plugin = plugin_name

        if best_plugin and best_score >= 80:   # same threshold as DSL interpreter
            return best_plugin, best_score

        # 3. Fallback to FTS5 (optional, kept for completeness)
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("""
            SELECT plugin_name, rank
            FROM triggers_fts
            WHERE triggers_fts MATCH ?
            ORDER BY rank
            LIMIT 1
        """, (text_lower,))
        row = cur.fetchone()
        conn.close()
        if row:
            plugin_name, rank = row
            confidence = max(0, min(100, int(100 - (rank * 2))))
            return plugin_name, confidence

        return None

    def list_plugins(self) -> List[str]:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT name FROM plugins ORDER BY name")
        plugins = [row[0] for row in cur]
        conn.close()
        return plugins