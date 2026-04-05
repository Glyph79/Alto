import os
import json
import time
import threading
from typing import Dict, Tuple, Optional
from ..config import config

HOT_TIMEOUT = config.getint('session', 'hot_timeout')
COLD_TIMEOUT = config.getint('session', 'cold_timeout')
CLEANUP_INTERVAL = config.getint('session', 'cleanup_interval')
SESSIONS_DIR = config.get('DEFAULT', 'sessions_dir')

os.makedirs(SESSIONS_DIR, exist_ok=True)

# Hot sessions: session_id -> (state dict, last_used timestamp)
_hot: Dict[str, Tuple[dict, float]] = {}
_lock = threading.Lock()


def _cold_path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def get_session(session_id: str, user_id: Optional[int] = None) -> dict:
    with _lock:
        now = time.time()

        # 1. Check hot cache
        if session_id in _hot:
            state, _ = _hot[session_id]

            # Migrate old format if necessary
            if "active_trees" not in state:
                state["active_trees"] = {}
            if "topics" not in state:
                state["topics"] = {}
            # Convert old group_id/path to active_trees format
            if "group_id" in state and state["group_id"] is not None:
                gid = state["group_id"]
                path = state.get("path", [])
                state["active_trees"][gid] = {"path": path, "last_used": now}
                del state["group_id"]
                if "path" in state:
                    del state["path"]

            # Update last used timestamp
            _hot[session_id] = (state, now)
            return state

        # 2. Try to restore from cold storage
        cold_file = _cold_path(session_id)
        if os.path.exists(cold_file):
            try:
                with open(cold_file, 'r') as f:
                    data = json.load(f)
                saved_at = data.get("saved_at", 0)
                if now - saved_at <= COLD_TIMEOUT:
                    state = data["state"]

                    # Migrate old format
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

                    # Move back to hot cache
                    _hot[session_id] = (state, now)
                    os.remove(cold_file)
                    return state
                else:
                    # Expired cold file
                    os.remove(cold_file)
            except Exception:
                pass

        # 3. Create new session
        new_state = {"topics": {}, "active_trees": {}}
        if user_id is not None:
            new_state["user_id"] = user_id
        _hot[session_id] = (new_state, now)
        return new_state


def save_session(session_id: str, state: dict) -> None:
    with _lock:
        now = time.time()
        # Ensure required keys exist
        if "active_trees" not in state:
            state["active_trees"] = {}
        if "topics" not in state:
            state["topics"] = {}
        _hot[session_id] = (state, now)


def _cleanup():
    """Background thread: move expired hot sessions to cold storage,
    and delete expired cold sessions."""
    while True:
        time.sleep(CLEANUP_INTERVAL)
        now = time.time()

        with _lock:
            # 1. Find hot sessions that have timed out
            expired_hot = []
            for sid, (state, last_used) in _hot.items():
                if now - last_used > HOT_TIMEOUT:
                    expired_hot.append((sid, state, last_used))

            # 2. Move them to cold storage
            for sid, state, last_used in expired_hot:
                # Remove from hot cache
                _hot.pop(sid, None)
                cold_file = _cold_path(sid)
                try:
                    with open(cold_file, 'w') as f:
                        json.dump({"state": state, "saved_at": last_used}, f)
                except Exception:
                    pass  # Log error if needed

        # 3. Clean up expired cold files (outside the lock to avoid long hold)
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
                    # If file is corrupt, remove it
                    try:
                        os.remove(path)
                    except Exception:
                        pass
        except Exception:
            pass


# Start the cleanup daemon thread
_cleaner_thread = threading.Thread(target=_cleanup, daemon=True)
_cleaner_thread.start()