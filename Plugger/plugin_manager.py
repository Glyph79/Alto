import os
import sqlite3
import json
import datetime
import msgpack
from typing import Optional, Dict, List, Any

PLUGINS_DIR = os.path.join(os.path.dirname(__file__), 'plugins')
os.makedirs(PLUGINS_DIR, exist_ok=True)

def _safe_filename(name: str) -> str:
    """Convert plugin name to a safe filename."""
    import re
    return re.sub(r'[^\w\-]', '_', name)

def _get_plugin_path(plugin_name: str) -> str:
    safe = _safe_filename(plugin_name)
    return os.path.join(PLUGINS_DIR, f"{safe}.plug")

def _get_connection(path: str) -> sqlite3.Connection:
    """Return a SQLite connection with optimal PRAGMA settings."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA cache_size = -5000")  # 5MB cache
    conn.execute("PRAGMA mmap_size = 30000000000")  # 30GB mmap (same as trainer)
    conn.row_factory = sqlite3.Row
    return conn

def _pack_array(arr: List) -> bytes:
    return msgpack.packb(arr, use_bin_type=True)

def _unpack_array(data: bytes) -> List:
    return msgpack.unpackb(data, raw=False)

def _init_plugin_db(conn: sqlite3.Connection, name: str, version: str, description: str):
    """Initialize a new plugin database schema."""
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
    # Optional: create index for triggers if needed later
    conn.execute('CREATE INDEX idx_triggers_phrase ON triggers(phrase)')
    conn.execute('''
        CREATE TABLE mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            fields TEXT NOT NULL,      -- JSON array of field names
            entries TEXT NOT NULL      -- JSON object mapping keys to field values
        )
    ''')
    conn.execute('CREATE INDEX idx_mappings_table ON mappings(table_name)')
    conn.execute('''
        CREATE TABLE response (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,         -- 'static' or 'api'
            data TEXT NOT NULL          -- JSON object (answers or url+templates)
        )
    ''')
    conn.execute('''
        CREATE TABLE tree_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER REFERENCES tree_nodes(id) ON DELETE CASCADE,
            branch_name TEXT NOT NULL,
            questions_blob BLOB NOT NULL,   -- msgpack array
            answers_blob BLOB NOT NULL      -- msgpack array
        )
    ''')
    conn.execute('CREATE INDEX idx_tree_parent ON tree_nodes(parent_id)')
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
    """Return list of plugins with basic info."""
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
    """Create a new plugin file."""
    path = _get_plugin_path(name)
    if os.path.exists(path):
        return {"error": f"Plugin '{name}' already exists"}
    conn = _get_connection(path)
    try:
        _init_plugin_db(conn, name, version, description)
        # Insert default response (static, empty answers)
        conn.execute("INSERT INTO response (type, data) VALUES (?, ?)",
                     ('static', json.dumps({'answers': []})))
        conn.commit()
        return {"status": "ok", "name": name}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def get_plugin(name: str) -> Dict:
    """Retrieve full plugin data as JSON."""
    path = _get_plugin_path(name)
    if not os.path.exists(path):
        return {"error": "Plugin not found"}
    conn = _get_connection(path)
    try:
        # Plugin info
        cur = conn.execute("SELECT name, version, description FROM plugin_info")
        row = cur.fetchone()
        if not row:
            return {"error": "Invalid plugin database"}
        plugin = dict(row)
        # Triggers
        cur = conn.execute("SELECT phrase FROM triggers ORDER BY id")
        plugin['triggers'] = [r[0] for r in cur]
        # Mappings
        cur = conn.execute("SELECT table_name, fields, entries FROM mappings ORDER BY id")
        plugin['mappings'] = {}
        for r in cur:
            plugin['mappings'][r[0]] = {
                'fields': json.loads(r[1]),
                'entries': json.loads(r[2])
            }
        # Response
        cur = conn.execute("SELECT type, data FROM response LIMIT 1")
        row = cur.fetchone()
        if row:
            plugin['response'] = json.loads(row[1])
            plugin['response']['type'] = row[0]
        else:
            plugin['response'] = {'type': 'static', 'answers': []}
        # Tree
        def load_tree(parent_id=None):
            cur = conn.execute(
                "SELECT id, branch_name, questions_blob, answers_blob FROM tree_nodes WHERE parent_id IS ? ORDER BY id",
                (parent_id,)
            )
            nodes = []
            for row in cur:
                node = {
                    'id': row[0],
                    'branch_name': row[1],
                    'questions': _unpack_array(row[2]),
                    'answers': _unpack_array(row[3]),
                    'children': load_tree(row[0])
                }
                nodes.append(node)
            return nodes
        plugin['tree'] = load_tree()
        return plugin
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def update_plugin(name: str, data: Dict) -> Dict:
    """Update an existing plugin."""
    path = _get_plugin_path(name)
    if not os.path.exists(path):
        return {"error": "Plugin not found"}
    conn = _get_connection(path)
    try:
        # Update info
        now = datetime.datetime.now().isoformat()
        conn.execute(
            "UPDATE plugin_info SET version = ?, description = ?, updated_at = ? WHERE name = ?",
            (data.get('version', ''), data.get('description', ''), now, name)
        )
        # Clear and re-insert triggers
        conn.execute("DELETE FROM triggers")
        for phrase in data.get('triggers', []):
            conn.execute("INSERT INTO triggers (phrase) VALUES (?)", (phrase,))
        # Clear and re-insert mappings
        conn.execute("DELETE FROM mappings")
        for table_name, table in data.get('mappings', {}).items():
            fields = json.dumps(table.get('fields', []))
            entries = json.dumps(table.get('entries', {}))
            conn.execute(
                "INSERT INTO mappings (table_name, fields, entries) VALUES (?, ?, ?)",
                (table_name, fields, entries)
            )
        # Update response
        response = data.get('response', {})
        resp_type = response.get('type', 'static')
        resp_data = {k: v for k, v in response.items() if k != 'type'}
        conn.execute("DELETE FROM response")
        conn.execute(
            "INSERT INTO response (type, data) VALUES (?, ?)",
            (resp_type, json.dumps(resp_data))
        )
        # Update tree
        conn.execute("DELETE FROM tree_nodes")
        def insert_tree(nodes, parent_id=None):
            for node in nodes:
                cur = conn.execute(
                    "INSERT INTO tree_nodes (parent_id, branch_name, questions_blob, answers_blob) VALUES (?, ?, ?, ?)",
                    (parent_id, node.get('branch_name', ''),
                     _pack_array(node.get('questions', [])),
                     _pack_array(node.get('answers', [])))
                )
                node_id = cur.lastrowid
                if node.get('children'):
                    insert_tree(node['children'], node_id)
        insert_tree(data.get('tree', []))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def delete_plugin(name: str) -> Dict:
    """Delete the plugin file."""
    path = _get_plugin_path(name)
    if not os.path.exists(path):
        return {"error": "Plugin not found"}
    try:
        os.remove(path)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}