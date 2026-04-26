# alto/core/jit_cache.py
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from ..config import config

class JITCache:
    """Server‑wide JIT cache using SQLite (disk or memory).
    
    - jit_ram_only_mode=True → in‑memory SQLite (RAM) – fastest, volatile.
    - jit_ram_only_mode=False → temp file in OS temp directory (disk) – persistent.
    
    Tables:
    - typo_cache: (word TEXT PRIMARY KEY, corrected TEXT, last_used REAL)
    - exact_cache: (key TEXT PRIMARY KEY, response TEXT NOT NULL, last_used REAL)
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
        """Create connection and tables, migrate old schema if needed.
        For disk mode, apply aggressive caching PRAGMAs for low latency.
        """
        if self._conn:
            self._conn.close()
        
        if self.jit_ram_only_mode:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            temp_dir = Path(tempfile.gettempdir()) / "alto_jit_cache"
            temp_dir.mkdir(exist_ok=True)
            db_path = temp_dir / "jit_cache.db"
            self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        
        # Always enable WAL
        self._conn.execute("PRAGMA journal_mode=WAL")
        
        # ---- Disk mode optimizations ----
        if not self.jit_ram_only_mode:
            # Increase SQLite cache size (20,000 pages = ~160 MB if page size 4KB)
            self._conn.execute("PRAGMA cache_size = 20000")
            # Memory-map the database file (256 MB) – reads become memory accesses
            self._conn.execute("PRAGMA mmap_size = 268435456")
            # Reduce fsync frequency – cache is not critical
            self._conn.execute("PRAGMA synchronous = NORMAL")
            # Store temporary tables in RAM
            self._conn.execute("PRAGMA temp_store = MEMORY")
            # Reduce WAL checkpoint frequency to avoid stalls
            self._conn.execute("PRAGMA wal_autocheckpoint = 10000")
        
        # Create typo_cache table
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
                # Old schema: sentence + response_data. Migrate.
                self._conn.execute("ALTER TABLE exact_cache RENAME TO exact_cache_old")
                self._conn.execute("""
                    CREATE TABLE exact_cache (
                        key TEXT PRIMARY KEY,
                        response TEXT NOT NULL,
                        last_used REAL NOT NULL
                    )
                """)
                self._conn.execute("""
                    INSERT INTO exact_cache (key, response, last_used)
                    SELECT sentence || '\x00', json_extract(response_data, '$.response'), last_used
                    FROM exact_cache_old
                """)
                self._conn.execute("DROP TABLE exact_cache_old")
                self._conn.commit()
        else:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS exact_cache (
                    key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    last_used REAL NOT NULL
                )
            """)
        
        self._conn.commit()
        
        # Preload exact_cache index into memory (forces SQLite to load the whole index)
        if not self.jit_ram_only_mode:
            self._conn.execute("SELECT count(*) FROM exact_cache")

    def set_ram_mode(self, enabled: bool):
        """Dynamically switch between RAM and disk storage. Clears existing cache."""
        with self._lock:
            if self.jit_ram_only_mode == enabled:
                return
            self.jit_ram_only_mode = enabled
            self._init_db()   # fresh DB, old cache lost

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

    def get_exact(self, sentence: str, context: str = "") -> Optional[str]:
        """Return cached response for a given normalized sentence and context."""
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
                return row[0]
            return None

    def set_exact(self, sentence: str, response: str, context: str = ""):
        """Store a response for a normalized sentence and context."""
        key = f"{sentence}\x00{context}"
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO exact_cache (key, response, last_used)
                   VALUES (?, ?, ?)""",
                (key, response, time.time())
            )
            self._conn.commit()
            self._evict_exact()

    def clear(self):
        with self._lock:
            self._conn.execute("DELETE FROM typo_cache")
            self._conn.execute("DELETE FROM exact_cache")
            self._conn.commit()