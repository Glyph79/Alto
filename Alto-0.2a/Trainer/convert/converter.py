"""
Main conversion functions (function‑based, no CLI).
Includes settings handling.
"""
import tempfile
import sqlite3
from pathlib import Path

from .db_readers.base import discover_reader
from .icf_importer import import_icf


def get_converter_settings():
    """Read converter settings from Trainer config."""
    from backend.config import config
    return {
        'batch_size': config.getint('converter', 'batch_size', fallback=100),
        # 'create_missing' is no longer used; always True in converter
    }


def update_converter_settings(batch_size=None, create_missing=None):
    """Update converter settings in Trainer config."""
    from backend.config import config, save_config
    if batch_size is not None:
        config.set('converter', 'batch_size', str(batch_size))
    # create_missing is ignored but kept for backward compatibility
    if create_missing is not None:
        config.set('converter', 'create_missing', str(create_missing))
    save_config(config)


def get_model_name_from_db(db_path: Path) -> str:
    """Extract model name from a legacy .db file."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.execute("SELECT name FROM model_info")
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass
    return db_path.stem


def export_legacy_db(db_path: Path, output_icf_dir: Path, batch_size: int = 100) -> dict:
    """
    Export a legacy .db file to an ICF directory.
    Returns a dict with counts of exported entities.
    """
    reader = discover_reader(db_path)
    if reader is None:
        raise RuntimeError(f"Unsupported or corrupted database: {db_path}")
    return reader.export_to_icf(db_path, output_icf_dir, batch_size)


def convert_legacy_db_to_rbm(db_path: Path, new_model_name: str = None, models_dir: Path = None, batch_size: int = None) -> str:
    """
    Convert a legacy .db file directly to a new .rbm model.
    If new_model_name is None, the name is read from the database.
    If batch_size is None, read from settings.
    Returns the path to the new .rbm container.
    """
    if models_dir is None:
        from backend.config import config
        models_dir = Path(config.get('DEFAULT', 'models_dir'))
    if batch_size is None:
        batch_size = get_converter_settings()['batch_size']
    if new_model_name is None:
        new_model_name = get_model_name_from_db(db_path)

    with tempfile.TemporaryDirectory() as tmp_icf_dir:
        export_legacy_db(db_path, Path(tmp_icf_dir), batch_size)
        # Always create missing topics/sections
        container_path = import_icf(Path(tmp_icf_dir), new_model_name, models_dir, create_missing=True)
    return container_path