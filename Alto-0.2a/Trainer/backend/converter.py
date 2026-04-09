import subprocess
import tempfile
import sys
import sqlite3
from pathlib import Path
from .config import config, save_config

CONVERTER_SCRIPT = Path(__file__).parent.parent / "tools" / "alto_convert.py"

def get_converter_settings():
    return {
        'batch_size': config.getint('converter', 'batch_size', fallback=100),
        'create_missing': config.getboolean('converter', 'create_missing', fallback=False),
    }

def update_converter_settings(batch_size=None, create_missing=None):
    if batch_size is not None:
        config.set('converter', 'batch_size', str(batch_size))
    if create_missing is not None:
        config.set('converter', 'create_missing', str(create_missing))
    save_config(config)

def get_model_name_from_db(db_file_path):
    """Extract model name from a legacy .db file."""
    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_file_path}?mode=ro", uri=True)
        cur = conn.execute("SELECT name FROM model_info")
        row = cur.fetchone()
        if row:
            return row[0]
    except Exception:
        pass
    finally:
        if conn:
            conn.close()
    # Fallback: use filename without extension
    return Path(db_file_path).stem

def convert_legacy_db_file(db_file_path, new_model_name=None, models_dir=None):
    """
    Convert a legacy .db file to a new .rbm model.
    If new_model_name is None, the name is read from the database (or filename).
    Returns path to the new .rbm container.
    """
    if models_dir is None:
        models_dir = config.get('DEFAULT', 'models_dir')
    if new_model_name is None:
        new_model_name = get_model_name_from_db(db_file_path)
    
    settings = get_converter_settings()
    batch_size = settings['batch_size']
    create_missing = settings['create_missing']

    with tempfile.TemporaryDirectory() as tmp_icf_dir:
        export_cmd = [
            sys.executable, str(CONVERTER_SCRIPT),
            "export-db",
            "--input-db", db_file_path,
            "--output-icf", tmp_icf_dir,
            "--batch-size", str(batch_size)
        ]
        result = subprocess.run(export_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Export failed: {result.stderr}")

        import_cmd = [
            sys.executable, str(CONVERTER_SCRIPT),
            "import-icf",
            "--input-icf", tmp_icf_dir,
            "--output-model", new_model_name,
            "--models-dir", str(models_dir)
        ]
        if create_missing:
            import_cmd.append("--create-missing")
        result = subprocess.run(import_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Import failed: {result.stderr}")

    from .utils.file_helpers import get_model_container_path
    container_path = get_model_container_path(new_model_name)
    return container_path