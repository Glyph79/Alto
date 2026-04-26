# alto/core/jit_cache.py
import json
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, Iterator, Tuple

from ..config import config

class JITCache:
    """Server‑wide JIT cache using SQLite (disk or memory).
    
    - jit_ram_only_mode=True → in‑memory SQLite (RAM) – fastest, volatile.
    - jit_ram_only_mode=False → temp file in OS temp directory (disk) – persistent.
    
    Tables:
    - typo_cache: (word TEXT PRIMARY KEY, corrected TEXT, last_used REAL)
    - exact_cache: (key TEXT PRIMARY KEY, response TEXT NOT NULL, last_used REAL)
                  response is a JSON string of a reference dict, e.g.
                  {"type":"node","id":123,"group_id":456} or {"type":"group","id":789}
    """
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._conn = None
        self.max_typo_entries = config.getint('ai', 'max_typo_cache', fallback=1000)
        self.max_exact_entries = config.getint('ai', 'max_exact_cache', fallback=500)
        self.jit_ram_only_mode = config.getboolean('ai', 'jit_ram_only_mode', fallback=True)
        self._init_db()

    def _init_db(self):
        """Create connection and tables, migrate old schema if needed."""
        if self._conn:
            self._conn.close()
        
        if self.jit_ram_only_mode:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            temp_dir = Path(tempfile.gettempdir()) / "alto_jit_cache"
            temp_dir.mkdir(exist_ok=True)
            db_path = temp_dir / "jit_cache.db"
            self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        
        self._conn.execute("PRAGMA journal_mode=WAL")
        
        if not self.jit_ram_only_mode:
            self._conn.execute("PRAGMA cache_size = 20000")
            self._conn.execute("PRAGMA mmap_size = 268435456")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute("PRAGMA temp_store = MEMORY")
            self._conn.execute("PRAGMA wal_autocheckpoint = 10000")
        
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS typo_cache (
                word TEXT PRIMARY KEY,
                corrected TEXT NOT NULL,
                last_used REAL NOT NULL
            )
        """)
        
        # Handle exact_cache migration and creation
        cur = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exact_cache'")
        if cur.fetchone():
            cur = self._conn.execute("PRAGMA table_info(exact_cache)")
            columns = [row[1] for row in cur]
            if 'key' not in columns:
                # Old schema: sentence + response_data (string). Drop and recreate.
                self._conn.execute("DROP TABLE exact_cache")
                self._create_exact_cache_table()
            else:
                # Check if any existing response is not valid JSON → clear incompatible entries
                cur = self._conn.execute("SELECT response FROM exact_cache LIMIT 1")
                row = cur.fetchone()
                if row:
                    try:
                        json.loads(row[0])
                    except (json.JSONDecodeError, TypeError):
                        self._conn.execute("DELETE FROM exact_cache")
                        self._conn.commit()
        else:
            self._create_exact_cache_table()
        
        self._conn.commit()
        
        if not self.jit_ram_only_mode:
            self._conn.execute("SELECT count(*) FROM exact_cache")

    def _create_exact_cache_table(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS exact_cache (
                key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                last_used REAL NOT NULL
            )
        """)

    def set_ram_mode(self, enabled: bool):
        with self._lock:
            if self.jit_ram_only_mode == enabled:
                return
            self.jit_ram_only_mode = enabled
            self._init_db()

    def set_max_sizes(self, max_typo: int, max_exact: int):
        with self._lock:
            self.max_typo_entries = max_typo
            self.max_exact_entries = max_exact
            self._evict_typo()
            self._evict_exact()

    def _evict_typo(self):
        if self.max_typo_entries <= 0:
            return
        cur = self._conn.execute("SELECT COUNT(*) FROM typo_cache")
        count = cur.fetchone()[0]
        if count > self.max_typo_entries:
            to_delete = count - self.max_typo_entries
            self._conn.execute("""
                DELETE FROM typo_cache 
                WHERE rowid IN (
                    SELECT rowid FROM typo_cache 
                    ORDER BY last_used ASC 
                    LIMIT ?
                )
            """, (to_delete,))
            self._conn.commit()

    def _evict_exact(self):
        if self.max_exact_entries <= 0:
            return
        cur = self._conn.execute("SELECT COUNT(*) FROM exact_cache")
        count = cur.fetchone()[0]
        if count > self.max_exact_entries:
            to_delete = count - self.max_exact_entries
            self._conn.execute("""
                DELETE FROM exact_cache 
                WHERE rowid IN (
                    SELECT rowid FROM exact_cache 
                    ORDER BY last_used ASC 
                    LIMIT ?
                )
            """, (to_delete,))
            self._conn.commit()

    # ----- Typo cache operations -----
    def get_typo(self, word: str) -> Optional[str]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT corrected FROM typo_cache WHERE word = ?",
                (word,)
            )
            row = cur.fetchone()
            if row:
                self._conn.execute(
                    "UPDATE typo_cache SET last_used = ? WHERE word = ?",
                    (time.time(), word)
                )
                self._conn.commit()
                return row[0]
            return None

    def set_typo(self, wrong: str, correct: str):
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO typo_cache (word, corrected, last_used)
                   VALUES (?, ?, ?)""",
                (wrong, correct, time.time())
            )
            self._conn.commit()
            self._evict_typo()

    def delete_typo(self, wrong: str):
        with self._lock:
            self._conn.execute("DELETE FROM typo_cache WHERE word = ?", (wrong,))
            self._conn.commit()

    def update_typo(self, wrong: str, new_correct: str):
        with self._lock:
            self._conn.execute(
                "UPDATE typo_cache SET corrected = ?, last_used = ? WHERE word = ?",
                (new_correct, time.time(), wrong)
            )
            self._conn.commit()

    def iter_typo_entries(self) -> Iterator[Tuple[str, str, float]]:
        """Yield (wrong, corrected, last_used) for all typo cache entries."""
        with self._lock:
            cur = self._conn.execute("SELECT word, corrected, last_used FROM typo_cache")
            for row in cur:
                yield row[0], row[1], row[2]

    # ----- Exact cache operations (reference‑based) -----
    def get_exact(self, sentence: str, context: str = "") -> Optional[Dict[str, Any]]:
        """Return cached reference dict for a given normalized sentence and context."""
        key = f"{sentence}\x00{context}"
        with self._lock:
            cur = self._conn.execute(
                "SELECT response FROM exact_cache WHERE key = ?",
                (key,)
            )
            row = cur.fetchone()
            if row:
                self._conn.execute(
                    "UPDATE exact_cache SET last_used = ? WHERE key = ?",
                    (time.time(), key)
                )
                self._conn.commit()
                try:
                    return json.loads(row[0])
                except json.JSONDecodeError:
                    self._conn.execute("DELETE FROM exact_cache WHERE key = ?", (key,))
                    self._conn.commit()
                    return None
            return None

    def set_exact(self, sentence: str, ref: Dict[str, Any], context: str = ""):
        """Store a reference dict for a given normalized sentence and context."""
        key = f"{sentence}\x00{context}"
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO exact_cache (key, response, last_used)
                   VALUES (?, ?, ?)""",
                (key, json.dumps(ref), time.time())
            )
            self._conn.commit()
            self._evict_exact()

    def delete_exact(self, key: str):
        with self._lock:
            self._conn.execute("DELETE FROM exact_cache WHERE key = ?", (key,))
            self._conn.commit()

    def update_exact(self, key: str, new_ref: Dict[str, Any]):
        with self._lock:
            self._conn.execute(
                "UPDATE exact_cache SET response = ?, last_used = ? WHERE key = ?",
                (json.dumps(new_ref), time.time(), key)
            )
            self._conn.commit()

    def iter_exact_entries(self) -> Iterator[Tuple[str, str, float]]:
        """Yield (key, response_json, last_used) for all exact cache entries."""
        with self._lock:
            cur = self._conn.execute("SELECT key, response, last_used FROM exact_cache")
            for row in cur:
                yield row[0], row[1], row[2]

    def clear(self):
        with self._lock:
            self._conn.execute("DELETE FROM typo_cache")
            self._conn.execute("DELETE FROM exact_cache")
            self._conn.commit()