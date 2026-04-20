import os
import re
from typing import Dict, List

PLUGINS_DIR = os.path.join(os.path.dirname(__file__), 'plugins')
os.makedirs(PLUGINS_DIR, exist_ok=True)

def _safe_filename(name: str) -> str:
    if not name:
        return None
    safe = re.sub(r'[^\w\-]', '_', name)
    safe = re.sub(r'_+', '_', safe)
    return safe

def _get_plugin_path(plugin_name: str) -> str:
    safe = _safe_filename(plugin_name)
    if not safe:
        return None
    return os.path.join(PLUGINS_DIR, f"{safe}.plug")

def _extract_metadata_and_triggers(code: str):
    lines = code.split('\n')
    name = version = author = description = ""
    triggers = []
    for line in lines:
        line = line.strip()
        if line.startswith('plugin name '):
            name = line[12:].strip('"')
        elif line.startswith('plugin version '):
            version = line[16:].strip('"')
        elif line.startswith('plugin author '):
            author = line[15:].strip('"')
        elif line.startswith('plugin description '):
            description = line[19:].strip('"')
        elif line.startswith('define input '):
            match = re.match(r'define input\s+"(.+)"', line)
            if match:
                triggers.append(match.group(1))
    return name, version, author, description, triggers

def list_plugins() -> List[Dict]:
    plugins = []
    if not os.path.exists(PLUGINS_DIR):
        return plugins
    for f in os.listdir(PLUGINS_DIR):
        if not f.endswith('.plug'):
            continue
        path = os.path.join(PLUGINS_DIR, f)
        try:
            with open(path, 'r', encoding='utf-8') as file:
                code = file.read()
            name, version, author, description, _ = _extract_metadata_and_triggers(code)
            if name:
                plugins.append({
                    "name": name,
                    "version": version or "0.0.0",
                    "description": description or ""
                })
        except Exception:
            continue
    return sorted(plugins, key=lambda x: x['name'])

def create_plugin(code: str) -> Dict:
    name, version, author, description, triggers = _extract_metadata_and_triggers(code)
    if not name:
        return {"error": "Missing 'plugin name' in code"}
    if not triggers:
        return {"error": "At least one 'define input' required"}

    path = _get_plugin_path(name)
    if not path or os.path.exists(path):
        return {"error": f"Plugin '{name}' already exists or invalid name"}

    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code)
        return {"status": "ok", "name": name}
    except Exception as e:
        return {"error": str(e)}

def get_plugin(name: str) -> Dict:
    path = _get_plugin_path(name)
    if not path or not os.path.exists(path):
        return {"error": "Plugin not found"}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            code = f.read()
        name, version, author, description, triggers = _extract_metadata_and_triggers(code)
        if not name:
            return {"error": "Invalid plugin file (missing plugin name)"}
        return {
            "name": name,
            "version": version or "",
            "author": author or "",
            "description": description or "",
            "triggers": triggers,
            "code": code
        }
    except Exception as e:
        return {"error": str(e)}

def update_plugin(name: str, code: str) -> Dict:
    new_name, version, author, description, triggers = _extract_metadata_and_triggers(code)
    if not new_name:
        return {"error": "Missing 'plugin name' in code"}

    old_path = _get_plugin_path(name)
    if not old_path or not os.path.exists(old_path):
        return {"error": "Plugin not found"}

    if new_name != name:
        new_path = _get_plugin_path(new_name)
        if not new_path:
            return {"error": "Invalid new plugin name"}
        if os.path.exists(new_path):
            return {"error": f"Plugin with name '{new_name}' already exists"}
        try:
            os.remove(old_path)
            with open(new_path, 'w', encoding='utf-8') as f:
                f.write(code)
            return {"status": "ok", "name": new_name, "renamed": True}
        except Exception as e:
            return {"error": str(e)}
    else:
        try:
            with open(old_path, 'w', encoding='utf-8') as f:
                f.write(code)
            return {"status": "ok", "name": name}
        except Exception as e:
            return {"error": str(e)}

def delete_plugin(name: str) -> Dict:
    path = _get_plugin_path(name)
    if not path or not os.path.exists(path):
        return {"error": "Plugin not found"}
    try:
        os.remove(path)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}