# alto/session.py
import os
import json
import time
import threading
import gc
from typing import Dict, Tuple, Optional
from .config import config, SESSIONS_DIR

HOT_TIMEOUT_MIN = config.getint('session', 'hot_timeout')
COLD_TIMEOUT_MIN = config.getint('session', 'cold_timeout')
CLEANUP_INTERVAL_MIN = config.getint('session', 'cleanup_interval')

HOT_TIMEOUT = HOT_TIMEOUT_MIN * 60
COLD_TIMEOUT = COLD_TIMEOUT_MIN * 60
CLEANUP_INTERVAL = CLEANUP_INTERVAL_MIN * 60

# Create subdirectories
USERS_SESSIONS_DIR = os.path.join(SESSIONS_DIR, 'users')
TESTS_SESSIONS_DIR = os.path.join(SESSIONS_DIR, 'tests')
os.makedirs(USERS_SESSIONS_DIR, exist_ok=True)
os.makedirs(TESTS_SESSIONS_DIR, exist_ok=True)

_hot: Dict[str, Tuple[dict, float]] = {}
_lock = threading.Lock()
_RELOAD_MARKER_PATH = os.path.join(os.path.dirname(SESSIONS_DIR), '.reload_marker')

def _cold_path(session_id: str) -> str:
    if session_id.startswith('__benchmark__'):
        return os.path.join(TESTS_SESSIONS_DIR, f"{session_id}.json")
    else:
        return os.path.join(USERS_SESSIONS_DIR, f"{session_id}.json")

def get_reload_marker_time() -> float:
    if os.path.exists(_RELOAD_MARKER_PATH):
        return os.path.getmtime(_RELOAD_MARKER_PATH)
    return 0

def validate_session_state(state: Dict, matcher) -> Dict:
    active_trees = state.get("active_trees", {})
    repaired_trees = {}
    for gid_str, tree_info in active_trees.items():
        gid = int(gid_str)
        try:
            group_data = matcher._get_group_data(gid)
        except Exception:
            continue
        path = tree_info.get("path", [])
        if not path:
            repaired_trees[gid_str] = tree_info
            continue
        valid_path = []
        for nid in path:
            try:
                node_data = matcher.get_node_data(nid)
                if not valid_path:
                    roots = matcher.adapter.get_root_nodes(gid)
                    if not any(r["id"] == nid for r in roots):
                        raise ValueError("not a root")
                else:
                    parent_node = matcher.get_node_data(valid_path[-1])
                    if not any(c["id"] == nid for c in parent_node.get("children", [])):
                        raise ValueError("not a child")
                valid_path.append(nid)
            except Exception:
                break
        if valid_path:
            tree_info["path"] = valid_path
            repaired_trees[gid_str] = tree_info
    state["active_trees"] = repaired_trees
    fb_id = state.get("current_fallback_id")
    if fb_id is not None:
        if not matcher.supports_feature("custom_fallbacks"):
            state["current_fallback_id"] = None
        else:
            try:
                matcher.get_fallback_answers(fb_id)
            except Exception:
                state["current_fallback_id"] = None
    state["_validated_after_reload"] = True
    return state

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
                if now - saved_at <= COLD_TIMEOUT or session_id.startswith('__benchmark__'):
                    state = data["state"]
                    marker_time = get_reload_marker_time()
                    if marker_time > saved_at and not state.get("_validated_after_reload"):
                        from .core.dispatcher import Dispatcher
                        from .config import config
                        model_name = config.get('DEFAULT', 'default_model')
                        temp_matcher = Dispatcher(model_name).matcher
                        state = validate_session_state(state, temp_matcher)
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
        # Immediately persist benchmark sessions to disk
        if session_id.startswith('__benchmark__'):
            cold_file = _cold_path(session_id)
            try:
                with open(cold_file, 'w') as f:
                    json.dump({"state": state, "saved_at": now}, f)
            except Exception as e:
                print(f"Failed to write cold session {session_id}: {e}")

def set_benchmark_result(model_name: str, result: dict) -> None:
    """Store the latest benchmark result for a model (overwrites previous)."""
    session_id = f"__benchmark__{model_name}"
    state = get_session(session_id, None)
    state["benchmark_result"] = result
    state["active_trees"] = {}
    state["topics"] = {}
    save_session(session_id, state)

def get_benchmark_result(model_name: str) -> Optional[dict]:
    """Retrieve the latest benchmark result for a model."""
    session_id = f"__benchmark__{model_name}"
    state = get_session(session_id, None)
    return state.get("benchmark_result")

def clear_benchmark_result(model_name: str) -> bool:
    """Clear benchmark result for a specific model."""
    session_id = f"__benchmark__{model_name}"
    with _lock:
        if session_id in _hot:
            state, last_used = _hot[session_id]
            state.pop("benchmark_result", None)
            state["active_trees"] = {}
            state["topics"] = {}
            _hot[session_id] = (state, last_used)
            return True
        else:
            cold_file = _cold_path(session_id)
            if os.path.exists(cold_file):
                try:
                    with open(cold_file, 'r') as f:
                        data = json.load(f)
                    data["state"].pop("benchmark_result", None)
                    data["state"]["active_trees"] = {}
                    data["state"]["topics"] = {}
                    with open(cold_file, 'w') as f:
                        json.dump(data, f)
                    return True
                except:
                    pass
            return False

def _cleanup():
    while True:
        time.sleep(CLEANUP_INTERVAL)
        now = time.time()
        with _lock:
            expired_hot = []
            for sid, (state, last_used) in _hot.items():
                if sid.startswith('__benchmark__'):
                    continue
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

        for dir_path in [USERS_SESSIONS_DIR]:
            if not os.path.exists(dir_path):
                continue
            for fname in os.listdir(dir_path):
                if not fname.endswith('.json'):
                    continue
                path = os.path.join(dir_path, fname)
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
        gc.collect()

_cleaner_thread = threading.Thread(target=_cleanup, daemon=True)
_cleaner_thread.start()