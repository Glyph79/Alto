"""
Base class for legacy database readers.
Each reader must implement export_to_icf().
"""
import abc
import sqlite3
from pathlib import Path
from typing import Dict


class DatabaseReader(abc.ABC):
    """Abstract base class for reading a legacy Alto database."""

    @abc.abstractmethod
    def get_version(self) -> str:
        """Return the version string this reader handles (e.g., '0.1a')."""
        pass

    @abc.abstractmethod
    def export_to_icf(self, db_path: Path, output_icf_dir: Path, batch_size: int = 100) -> Dict[str, int]:
        """
        Read the legacy .db file and write its contents as an ICF directory.
        Returns a dict with counts: {'sections': n, 'topics': n, ...}
        """
        pass

    @staticmethod
    def _open_connection(db_path: Path) -> sqlite3.Connection:
        """Open a read‑only connection to the legacy database."""
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn


def discover_reader(db_path: Path):
    """
    Dynamically load the appropriate reader for the given legacy .db file.
    Returns an instance of the reader, or None if version is unsupported.
    """
    import importlib
    import sys

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.execute("SELECT alto_version FROM model_info")
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        version = row[0]
    except Exception:
        return None

    # Map version string to module name (e.g., "0.1a" -> "v0_1a")
    module_name = version.replace('.', '_')
    module_name = f"v{module_name}"

    try:
        module = importlib.import_module(f"convert.db_readers.{module_name}")
        reader_class = getattr(module, f"ReaderV{module_name[1:]}")
        return reader_class()
    except (ImportError, AttributeError):
        return None