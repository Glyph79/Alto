#!/usr/bin/env python3
"""
Alto Trainer – param‑based CLI.
Usage:
  trainer.py <command> [options]          # single command
  trainer.py --interactive                 # read JSON commands from stdin
"""

import argparse
import json
import os
import sys
import datetime
import lmdb
from typing import Dict, Any

# ----------------------------------------------------------------------
# LMDB setup (global, reused across commands)
# ----------------------------------------------------------------------
LMDB_PATH = os.path.join(os.path.dirname(__file__), "lmdb")
os.makedirs(LMDB_PATH, exist_ok=True)
env = lmdb.open(LMDB_PATH, map_size=10_737_418_240, max_dbs=100)

def _get_model_db(model_name: str, write: bool = False):
    return env.open_db(key=model_name.encode(), create=True)

# ----------------------------------------------------------------------
# Low‑level database helpers
# ----------------------------------------------------------------------
def _list_models() -> list:
    with env.begin() as txn:
        main_db = env.open_db()
        data = txn.get(b'models', db=main_db)
        return json.loads(data.decode()) if data else []

def _save_models(models: list):
    with env.begin(write=True) as txn:
        main_db = env.open_db()
        txn.put(b'models', json.dumps(models).encode(), db=main_db)

def _load_model_meta(model_name: str) -> dict:
    db = _get_model_db(model_name)
    with env.begin() as txn:
        meta_bytes = txn.get(b'meta', db=db)
        if not meta_bytes:
            raise ValueError(f"Model '{model_name}' not found")
        return json.loads(meta_bytes.decode())

def _save_model_meta(model_name: str, meta: dict):
    db = _get_model_db(model_name, write=True)
    with env.begin(write=True) as txn:
        txn.put(b'meta', json.dumps(meta, separators=(',', ':')).encode(), db=db)

def _get_group_ids(model_name: str) -> list:
    db = _get_model_db(model_name)
    with env.begin() as txn:
        data = txn.get(b'group_ids', db=db)
        return json.loads(data.decode()) if data else []

def _save_group_ids(model_name: str, ids: list):
    db = _get_model_db(model_name, write=True)
    with env.begin(write=True) as txn:
        txn.put(b'group_ids', json.dumps(ids).encode(), db=db)

def _get_next_group_id(model_name: str) -> int:
    db = _get_model_db(model_name)
    with env.begin() as txn:
        data = txn.get(b'next_group_id', db=db)
        if data:
            return int.from_bytes(data, 'big')
        return 1

def _set_next_group_id(model_name: str, next_id: int):
    db = _get_model_db(model_name, write=True)
    with env.begin(write=True) as txn:
        txn.put(b'next_group_id', next_id.to_bytes(8, 'big'), db=db)

def _get_group(model_name: str, gid: int) -> dict:
    db = _get_model_db(model_name)
    with env.begin() as txn:
        key = f"group:{gid}".encode()
        data = txn.get(key, db=db)
        if not data:
            raise KeyError(f"Group {gid} not found")
        return json.loads(data.decode())

def _put_group(model_name: str, gid: int, group_data: dict):
    db = _get_model_db(model_name, write=True)
    with env.begin(write=True) as txn:
        key = f"group:{gid}".encode()
        txn.put(key, json.dumps(group_data, separators=(',', ':')).encode(), db=db)

def _delete_group(model_name: str, gid: int):
    db = _get_model_db(model_name, write=True)
    with env.begin(write=True) as txn:
        key = f"group:{gid}".encode()
        txn.delete(key, db=db)

# ----------------------------------------------------------------------
# Command handlers (each returns a dict to be JSON‑serialized)
# ----------------------------------------------------------------------
def cmd_list_models(**kwargs):
    return _list_models()

def cmd_create_model(name, description="", author="", version="1.0.0", **kwargs):
    models = _list_models()
    if name in models:
        return {"error": f"Model '{name}' already exists"}
    now = datetime.datetime.now().isoformat()
    meta = {
        "name": name,
        "description": description,
        "author": author,
        "version": version,
        "created_at": now,
        "updated_at": now,
        "sections": ["General", "Technical", "Creative"]
    }
    db = _get_model_db(name, write=True)
    with env.begin(write=True) as txn:
        txn.put(b'meta', json.dumps(meta).encode(), db=db)
        txn.put(b'group_ids', json.dumps([]).encode(), db=db)
        txn.put(b'next_group_id', (1).to_bytes(8, 'big'), db=db)
    models.append(name)
    _save_models(models)
    return {"status": "ok", "model": meta}

def cmd_get_model(name, **kwargs):
    try:
        meta = _load_model_meta(name)
        group_ids = _get_group_ids(name)
        groups = []
        for gid in group_ids:
            groups.append(_get_group(name, gid))
        return {**meta, "qa_groups": groups}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_model(name, description=None, author=None, version=None, **kwargs):
    try:
        meta = _load_model_meta(name)
        if description is not None:
            meta["description"] = description
        if author is not None:
            meta["author"] = author
        if version is not None:
            meta["version"] = version
        meta["updated_at"] = datetime.datetime.now().isoformat()
        _save_model_meta(name, meta)
        return {"status": "ok", "model": meta}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_model(name, **kwargs):
    models = _list_models()
    if name not in models:
        return {"error": f"Model '{name}' not found"}
    db = _get_model_db(name)
    with env.begin(write=True) as txn:
        txn.drop(db, delete=True)
    models.remove(name)
    _save_models(models)
    return {"status": "ok"}

def cmd_add_group(name, data, **kwargs):
    try:
        group_data = json.loads(data)
        group_data.setdefault("group_name", "New Group")
        group_data.setdefault("questions", [])
        group_data.setdefault("answers", [])
        group_data.setdefault("topic", "general")
        group_data.setdefault("priority", "medium")
        group_data.setdefault("section", "")
        group_data.setdefault("follow_ups", [])

        next_id = _get_next_group_id(name)
        _put_group(name, next_id, group_data)
        ids = _get_group_ids(name)
        ids.append(next_id)
        _save_group_ids(name, ids)
        _set_next_group_id(name, next_id + 1)
        return {"status": "ok", "group_id": next_id}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_group(name, index, data, **kwargs):
    try:
        group_data = json.loads(data)
        ids = _get_group_ids(name)
        idx = int(index)
        if idx < 0 or idx >= len(ids):
            return {"error": "Group index out of range"}
        gid = ids[idx]
        _put_group(name, gid, group_data)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_group(name, index, **kwargs):
    try:
        ids = _get_group_ids(name)
        idx = int(index)
        if idx < 0 or idx >= len(ids):
            return {"error": "Group index out of range"}
        gid = ids.pop(idx)
        _delete_group(name, gid)
        _save_group_ids(name, ids)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_add_question(name, index, text, **kwargs):
    try:
        ids = _get_group_ids(name)
        idx = int(index)
        if idx < 0 or idx >= len(ids):
            return {"error": "Group index out of range"}
        gid = ids[idx]
        group = _get_group(name, gid)
        group.setdefault("questions", []).append(text)
        _put_group(name, gid, group)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_question(name, index, qidx, text, **kwargs):
    try:
        ids = _get_group_ids(name)
        idx = int(index)
        if idx < 0 or idx >= len(ids):
            return {"error": "Group index out of range"}
        gid = ids[idx]
        group = _get_group(name, gid)
        q = int(qidx)
        if q < 0 or q >= len(group.get("questions", [])):
            return {"error": "Question index out of range"}
        group["questions"][q] = text
        _put_group(name, gid, group)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_question(name, index, qidx, **kwargs):
    try:
        ids = _get_group_ids(name)
        idx = int(index)
        if idx < 0 or idx >= len(ids):
            return {"error": "Group index out of range"}
        gid = ids[idx]
        group = _get_group(name, gid)
        q = int(qidx)
        if q < 0 or q >= len(group.get("questions", [])):
            return {"error": "Question index out of range"}
        del group["questions"][q]
        _put_group(name, gid, group)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_add_answer(name, index, text, **kwargs):
    try:
        ids = _get_group_ids(name)
        idx = int(index)
        if idx < 0 or idx >= len(ids):
            return {"error": "Group index out of range"}
        gid = ids[idx]
        group = _get_group(name, gid)
        group.setdefault("answers", []).append(text)
        _put_group(name, gid, group)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_update_answer(name, index, aidx, text, **kwargs):
    try:
        ids = _get_group_ids(name)
        idx = int(index)
        if idx < 0 or idx >= len(ids):
            return {"error": "Group index out of range"}
        gid = ids[idx]
        group = _get_group(name, gid)
        a = int(aidx)
        if a < 0 or a >= len(group.get("answers", [])):
            return {"error": "Answer index out of range"}
        group["answers"][a] = text
        _put_group(name, gid, group)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_answer(name, index, aidx, **kwargs):
    try:
        ids = _get_group_ids(name)
        idx = int(index)
        if idx < 0 or idx >= len(ids):
            return {"error": "Group index out of range"}
        gid = ids[idx]
        group = _get_group(name, gid)
        a = int(aidx)
        if a < 0 or a >= len(group.get("answers", [])):
            return {"error": "Answer index out of range"}
        del group["answers"][a]
        _put_group(name, gid, group)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_followups(name, index, **kwargs):
    try:
        ids = _get_group_ids(name)
        idx = int(index)
        if idx < 0 or idx >= len(ids):
            return {"error": "Group index out of range"}
        gid = ids[idx]
        group = _get_group(name, gid)
        return group.get("follow_ups", [])
    except Exception as e:
        return {"error": str(e)}

def cmd_save_followups(name, index, data, **kwargs):
    try:
        ids = _get_group_ids(name)
        idx = int(index)
        if idx < 0 or idx >= len(ids):
            return {"error": "Group index out of range"}
        gid = ids[idx]
        group = _get_group(name, gid)
        group["follow_ups"] = json.loads(data)
        _put_group(name, gid, group)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_add_section(name, section, **kwargs):
    try:
        meta = _load_model_meta(name)
        if section not in meta["sections"]:
            meta["sections"].append(section)
            meta["updated_at"] = datetime.datetime.now().isoformat()
            _save_model_meta(name, meta)
            return {"status": "ok"}
        else:
            return {"error": "Section already exists"}
    except Exception as e:
        return {"error": str(e)}

def cmd_rename_section(name, old, new, **kwargs):
    try:
        meta = _load_model_meta(name)
        if old not in meta["sections"]:
            return {"error": f"Section '{old}' not found"}
        if new in meta["sections"] and new != old:
            return {"error": f"Section '{new}' already exists"}
        idx = meta["sections"].index(old)
        meta["sections"][idx] = new
        meta["updated_at"] = datetime.datetime.now().isoformat()
        _save_model_meta(name, meta)
        # Update groups
        ids = _get_group_ids(name)
        for gid in ids:
            group = _get_group(name, gid)
            if group.get("section") == old:
                group["section"] = new
                _put_group(name, gid, group)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_section(name, section, action="uncategorized", target=None, **kwargs):
    try:
        meta = _load_model_meta(name)
        if section not in meta["sections"]:
            return {"error": f"Section '{section}' not found"}
        ids = _get_group_ids(name)
        for gid in ids:
            group = _get_group(name, gid)
            if group.get("section") == section:
                if action == "uncategorized":
                    group["section"] = ""
                elif action == "move" and target:
                    group["section"] = target
                _put_group(name, gid, group)
        if action == "delete":
            new_ids = []
            for gid in ids:
                group = _get_group(name, gid)
                if group.get("section") != section:
                    new_ids.append(gid)
                else:
                    _delete_group(name, gid)
            _save_group_ids(name, new_ids)
        meta["sections"].remove(section)
        meta["updated_at"] = datetime.datetime.now().isoformat()
        _save_model_meta(name, meta)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_import(name, file, **kwargs):
    try:
        with open(file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and "qa_groups" in data:
            groups = data["qa_groups"]
            if "sections" in data:
                meta = _load_model_meta(name)
                meta["sections"] = data["sections"]
                meta["updated_at"] = datetime.datetime.now().isoformat()
                _save_model_meta(name, meta)
        elif isinstance(data, list):
            groups = data
        else:
            groups = [data]
        count = 0
        for g in groups:
            next_id = _get_next_group_id(name)
            _put_group(name, next_id, g)
            ids = _get_group_ids(name)
            ids.append(next_id)
            _save_group_ids(name, ids)
            _set_next_group_id(name, next_id + 1)
            count += 1
        return {"status": "ok", "imported": count}
    except Exception as e:
        return {"error": str(e)}

def cmd_export(name, **kwargs):
    try:
        meta = _load_model_meta(name)
        ids = _get_group_ids(name)
        groups = []
        for gid in ids:
            groups.append(_get_group(name, gid))
        return {**meta, "qa_groups": groups}
    except Exception as e:
        return {"error": str(e)}

# ----------------------------------------------------------------------
# Command registry
# ----------------------------------------------------------------------
COMMANDS = {
    "list-models":      cmd_list_models,
    "create-model":     cmd_create_model,
    "get-model":        cmd_get_model,
    "update-model":     cmd_update_model,
    "delete-model":     cmd_delete_model,
    "add-group":        cmd_add_group,
    "update-group":     cmd_update_group,
    "delete-group":     cmd_delete_group,
    "add-question":     cmd_add_question,
    "update-question":  cmd_update_question,
    "delete-question":  cmd_delete_question,
    "add-answer":       cmd_add_answer,
    "update-answer":    cmd_update_answer,
    "delete-answer":    cmd_delete_answer,
    "get-followups":    cmd_get_followups,
    "save-followups":   cmd_save_followups,
    "add-section":      cmd_add_section,
    "rename-section":   cmd_rename_section,
    "delete-section":   cmd_delete_section,
    "import":           cmd_import,
    "export":           cmd_export,
}

# ----------------------------------------------------------------------
# Interactive mode
# ----------------------------------------------------------------------
def interactive_loop():
    """Read JSON lines from stdin, dispatch commands, print JSON results."""
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line or line == "exit":
            break
        try:
            req = json.loads(line)
            cmd = req.get("command")
            kwargs = req.get("args", {})
            if cmd not in COMMANDS:
                result = {"error": f"Unknown command: {cmd}"}
            else:
                result = COMMANDS[cmd](**kwargs)
        except Exception as e:
            result = {"error": str(e)}
        print(json.dumps(result), flush=True)

# ----------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------
def main():
    if "--interactive" in sys.argv:
        interactive_loop()
        return

    parser = argparse.ArgumentParser(description="Alto Trainer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Dynamically create subparsers for each command
    p = subparsers.add_parser("list-models")
    p.set_defaults(func=cmd_list_models)

    p = subparsers.add_parser("create-model")
    p.add_argument("name")
    p.add_argument("--description", default="")
    p.add_argument("--author", default="")
    p.add_argument("--version", default="1.0.0")
    p.set_defaults(func=cmd_create_model)

    p = subparsers.add_parser("get-model")
    p.add_argument("name")
    p.set_defaults(func=cmd_get_model)

    p = subparsers.add_parser("update-model")
    p.add_argument("name")
    p.add_argument("--description")
    p.add_argument("--author")
    p.add_argument("--version")
    p.set_defaults(func=cmd_update_model)

    p = subparsers.add_parser("delete-model")
    p.add_argument("name")
    p.set_defaults(func=cmd_delete_model)

    p = subparsers.add_parser("add-group")
    p.add_argument("name")
    p.add_argument("--data", required=True)
    p.set_defaults(func=cmd_add_group)

    p = subparsers.add_parser("update-group")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("--data", required=True)
    p.set_defaults(func=cmd_update_group)

    p = subparsers.add_parser("delete-group")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.set_defaults(func=cmd_delete_group)

    p = subparsers.add_parser("add-question")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_add_question)

    p = subparsers.add_parser("update-question")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("qidx", type=int)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_update_question)

    p = subparsers.add_parser("delete-question")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("qidx", type=int)
    p.set_defaults(func=cmd_delete_question)

    p = subparsers.add_parser("add-answer")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_add_answer)

    p = subparsers.add_parser("update-answer")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("aidx", type=int)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_update_answer)

    p = subparsers.add_parser("delete-answer")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("aidx", type=int)
    p.set_defaults(func=cmd_delete_answer)

    p = subparsers.add_parser("get-followups")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.set_defaults(func=cmd_get_followups)

    p = subparsers.add_parser("save-followups")
    p.add_argument("name")
    p.add_argument("index", type=int)
    p.add_argument("--data", required=True)
    p.set_defaults(func=cmd_save_followups)

    p = subparsers.add_parser("add-section")
    p.add_argument("name")
    p.add_argument("--section", required=True)
    p.set_defaults(func=cmd_add_section)

    p = subparsers.add_parser("rename-section")
    p.add_argument("name")
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.set_defaults(func=cmd_rename_section)

    p = subparsers.add_parser("delete-section")
    p.add_argument("name")
    p.add_argument("--section", required=True)
    p.add_argument("--action", choices=["uncategorized", "delete", "move"], default="uncategorized")
    p.add_argument("--target")
    p.set_defaults(func=cmd_delete_section)

    p = subparsers.add_parser("import")
    p.add_argument("name")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_import)

    p = subparsers.add_parser("export")
    p.add_argument("name")
    p.set_defaults(func=cmd_export)

    args = parser.parse_args()
    kwargs = {k: v for k, v in vars(args).items() if k not in ('func', 'command') and v is not None}
    try:
        result = args.func(**kwargs)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()