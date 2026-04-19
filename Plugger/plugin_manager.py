import os
import sqlite3
import json
import datetime
import msgpack
from typing import Optional, Dict, List, Any

PLUGINS_DIR = os.path.join(os.path.dirname(__file__), 'plugins')
os.makedirs(PLUGINS_DIR, exist_ok=True)

def _safe_filename(name: str) -> str:
    import re
    return re.sub(r'[^\w\-]', '_', name)

def _get_plugin_path(plugin_name: str) -> str:
    safe = _safe_filename(plugin_name)
    return os.path.join(PLUGINS_DIR, f"{safe}.plug")

def _get_connection(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA cache_size = -5000")
    conn.execute("PRAGMA mmap_size = 30000000000")
    conn.row_factory = sqlite3.Row
    return conn

def _pack_array(arr: List) -> bytes:
    return msgpack.packb(arr, use_bin_type=True)

def _unpack_array(data: bytes) -> List:
    return msgpack.unpackb(data, raw=False)

def _init_plugin_db(conn: sqlite3.Connection, name: str, version: str, description: str):
    conn.execute('''
        CREATE TABLE plugin_info (
            name TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phrase TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE script (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_blob BLOB NOT NULL
        )
    ''')
    conn.execute("INSERT INTO script (script_blob) VALUES ('{}')")
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "INSERT INTO plugin_info (name, version, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (name, version, description, now, now)
    )
    conn.commit()

# ------------------------------------------------------------------
# Plugin CRUD
# ------------------------------------------------------------------
def list_plugins() -> List[Dict]:
    plugins = []
    if not os.path.exists(PLUGINS_DIR):
        return plugins
    for f in os.listdir(PLUGINS_DIR):
        if f.endswith('.plug'):
            path = os.path.join(PLUGINS_DIR, f)
            try:
                conn = _get_connection(path)
                cur = conn.execute("SELECT name, version, description FROM plugin_info")
                row = cur.fetchone()
                if row:
                    plugins.append({"name": row[0], "version": row[1], "description": row[2]})
                conn.close()
            except Exception:
                continue
    return sorted(plugins, key=lambda x: x['name'])

def create_plugin(name: str, version: str, description: str) -> Dict:
    path = _get_plugin_path(name)
    if os.path.exists(path):
        return {"error": f"Plugin '{name}' already exists"}
    conn = _get_connection(path)
    try:
        _init_plugin_db(conn, name, version, description)
        conn.commit()
        return {"status": "ok", "name": name}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def get_plugin(name: str) -> Dict:
    path = _get_plugin_path(name)
    if not os.path.exists(path):
        return {"error": "Plugin not found"}
    conn = _get_connection(path)
    try:
        cur = conn.execute("SELECT name, version, description FROM plugin_info")
        row = cur.fetchone()
        if not row:
            return {"error": "Invalid plugin database"}
        plugin = dict(row)
        cur = conn.execute("SELECT phrase FROM triggers ORDER BY id")
        plugin['triggers'] = [r[0] for r in cur]
        cur = conn.execute("SELECT script_blob FROM script LIMIT 1")
        script_row = cur.fetchone()
        plugin['script_json'] = script_row[0].decode('utf-8') if script_row and script_row[0] else '{}'
        return plugin
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def update_plugin(name: str, data: Dict) -> Dict:
    path = _get_plugin_path(name)
    if not os.path.exists(path):
        return {"error": "Plugin not found"}
    conn = _get_connection(path)
    try:
        now = datetime.datetime.now().isoformat()
        conn.execute(
            "UPDATE plugin_info SET version = ?, description = ?, updated_at = ? WHERE name = ?",
            (data.get('version', ''), data.get('description', ''), now, name)
        )
        conn.execute("DELETE FROM triggers")
        for phrase in data.get('triggers', []):
            conn.execute("INSERT INTO triggers (phrase) VALUES (?)", (phrase,))
        script_json = data.get('script_json', '{}')
        conn.execute("UPDATE script SET script_blob = ?", (script_json.encode('utf-8'),))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def delete_plugin(name: str) -> Dict:
    path = _get_plugin_path(name)
    if not os.path.exists(path):
        return {"error": "Plugin not found"}
    try:
        os.remove(path)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}