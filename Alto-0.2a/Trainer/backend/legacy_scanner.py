import os
import shutil
import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_valid_legacy_db(db_path):
    """
    Check if a .db file is a valid Alto v0.1 model by reading alto_version from model_info.
    """
    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        # Verify model_info table exists
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model_info'")
        if not cur.fetchone():
            logger.warning(f"{db_path}: no model_info table")
            return False
        # Read alto_version
        cur = conn.execute("SELECT alto_version FROM model_info")
        row = cur.fetchone()
        if row and row[0] and row[0].startswith("0.1"):
            return True
        logger.warning(f"{db_path}: alto_version is {row[0] if row else 'missing'}, not 0.1a")
        return False
    except Exception as e:
        logger.error(f"Error checking {db_path}: {e}")
        return False
    finally:
        if conn:
            conn.close()

def scan_legacy_models(models_dir):
    """Return list of .db files in models_dir that are valid legacy models."""
    models_path = Path(models_dir)
    if not models_path.exists():
        return []
    legacy = []
    for f in models_path.glob("*.db"):
        if is_valid_legacy_db(f):
            legacy.append(str(f))
        else:
            logger.info(f"Skipping {f.name}: not a valid legacy model")
    return legacy

def backup_model(db_path, backup_dir):
    """Copy a .db file to backup folder. Returns backup path."""
    backup_path = Path(backup_dir) / Path(db_path).name
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, backup_path)
    return str(backup_path)

def convert_legacy_model(db_path, new_model_name, models_dir, backup_dir=None):
    """
    Convert a legacy .db file to a new .rbm model.
    If backup_dir is given, copy the original there first.
    Returns new model name and path, or raises exception.
    """
    from .converter import convert_legacy_db_file
    if backup_dir:
        backup_model(db_path, backup_dir)
    container_path = convert_legacy_db_file(db_path, new_model_name, models_dir)
    os.remove(db_path)
    return new_model_name, container_path