import os
import json
import time
import threading
import gc
from typing import Dict, Tuple, Optional
from ..config import config

HOT_TIMEOUT = config.getint('session', 'hot_timeout')
COLD_TIMEOUT = config.getint('session', 'cold_timeout')
CLEANUP_INTERVAL = config.getint('session', 'cleanup_interval')
SESSIONS_DIR = config.get('DEFAULT', 'sessions_dir')

os.makedirs(SESSIONS_DIR, exist_ok=True)

_hot: Dict[str, Tuple[dict, float]] = {}
_lock = threading.Lock()


def _cold_path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def get_session(session_id: str, user_id: Optional[int] = None) -> dict:
    with _lock:
        now = time.time()

        if session_id in _hot:
            state, _ = _hot[session_id]
            if "active_trees" not in state:
                state["active_trees"] = {}
            if "topics" not in state:
                state["topics"] = {}
            if "group_id" in state and state["group_id"] is not None:
                gid = state["group_id"]
                path = state.get("path", [])
                state["active_trees"][gid] = {"path": path, "last_used": now}
                del state["group_id"]
                if "path" in state:
                    del state["path"]
            _hot[session_id] = (state, now)
            return state

        cold_file = _cold_path(session_id)
        if os.path.exists(cold_file):
            try:
                with open(cold_file, 'r') as f:
                    data = json.load(f)
                saved_at = data.get("saved_at", 0)
                if now - saved_at <= COLD_TIMEOUT:
                    state = data["state"]
                    if "active_trees" not in state:
                        state["active_trees"] = {}
                    if "topics" not in state:
                        state["topics"] = {}
                    if "group_id" in state and state["group_id"] is not None:
                        gid = state["group_id"]
                        path = state.get("path", [])
                        state["active_trees"][gid] = {"path": path, "last_used": saved_at}
                        del state["group_id"]
                        if "path" in state:
                            del state["path"]
                    _hot[session_id] = (state, now)
                    os.remove(cold_file)
                    return state
                else:
                    os.remove(cold_file)
            except Exception:
                pass

        new_state = {"topics": {}, "active_trees": {}}
        if user_id is not None:
            new_state["user_id"] = user_id
        _hot[session_id] = (new_state, now)
        return new_state


def save_session(session_id: str, state: dict) -> None:
    with _lock:
        now = time.time()
        if "active_trees" not in state:
            state["active_trees"] = {}
        if "topics" not in state:
            state["topics"] = {}
        _hot[session_id] = (state, now)


def _cleanup():
    gc_counter = 0
    while True:
        time.sleep(CLEANUP_INTERVAL)
        now = time.time()

        with _lock:
            expired_hot = []
            for sid, (state, last_used) in _hot.items():
                if now - last_used > HOT_TIMEOUT:
                    expired_hot.append((sid, state, last_used))

            for sid, state, last_used in expired_hot:
                _hot.pop(sid, None)
                cold_file = _cold_path(sid)
                try:
                    with open(cold_file, 'w') as f:
                        json.dump({"state": state, "saved_at": last_used}, f)
                except Exception:
                    pass

        try:
            for fname in os.listdir(SESSIONS_DIR):
                if not fname.endswith('.json'):
                    continue
                path = os.path.join(SESSIONS_DIR, fname)
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                    saved_at = data.get("saved_at", 0)
                    if now - saved_at > COLD_TIMEOUT:
                        os.remove(path)
                except Exception:
                    try:
                        os.remove(path)
                    except Exception:
                        pass
        except Exception:
            pass

        gc_counter += 1
        if gc_counter >= 10:
            gc.collect()
            gc_counter = 0


_cleaner_thread = threading.Thread(target=_cleanup, daemon=True)
_cleaner_thread.start()