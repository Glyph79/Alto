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
        """Create database schema if not exists."""
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

    def _table_exists(self, conn, table_name: str) -> bool:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cur.fetchone() is not None

    def rebuild_if_changed(self):
        """Check if any plugin file changed or the DB is missing tables; rebuild if needed."""
        current_mtime = 0
        any_changed = False

        # First, check if the DB file exists and has the required tables
        if not os.path.exists(self.db_path):
            self._rebuild_full()
            return

        try:
            conn = sqlite3.connect(self.db_path)
            # Check for required tables
            if not (self._table_exists(conn, 'plugins') and
                    self._table_exists(conn, 'triggers') and
                    self._table_exists(conn, 'triggers_fts')):
                conn.close()
                self._rebuild_full()
                return
            conn.close()
        except sqlite3.DatabaseError:
            # Corrupt database – rebuild
            self._rebuild_full()
            return

        for fname in os.listdir(self.plugins_dir):
            if not fname.endswith('.plug'):
                continue
            path = os.path.join(self.plugins_dir, fname)
            mtime = os.path.getmtime(path)
            current_mtime = max(current_mtime, mtime)
            try:
                conn = sqlite3.connect(self.db_path)
                cur = conn.execute("SELECT file_mtime, file_hash FROM plugins WHERE name = ?", (fname[:-5],))
                row = cur.fetchone()
                conn.close()
            except sqlite3.OperationalError:
                # Table missing despite earlier check – rebuild
                self._rebuild_full()
                return
            if not row or row[0] < mtime or row[1] != self._get_plugin_hash(path):
                any_changed = True
                break

        if any_changed or current_mtime > self._get_last_build_mtime():
            self._rebuild_full()

    def _rebuild_full(self):
        """Delete the old index and rebuild from scratch."""
        # Remove the old database file if it exists
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        # Recreate schema
        self._init_db()
        conn = sqlite3.connect(self.db_path)

        # Clear any cached triggers
        self._cached_triggers = None

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
        # Update the last build timestamp
        os.utime(self.db_path, None)

    def force_rebuild(self):
        """Manually trigger a full rebuild (used by /plugin reload)."""
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
            score = fuzz.token_set_ratio(text_lower, trigger.lower())
            if score > best_score:
                best_score = score
                best_plugin = plugin_name

        if best_plugin and best_score >= 80:
            return best_plugin, best_score

        # 3. Fallback to FTS5 (optional)
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