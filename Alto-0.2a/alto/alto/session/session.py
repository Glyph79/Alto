import os
import json
import time
import threading
import heapq
from typing import Dict, Tuple, Optional
from alto.config import config

HOT_TIMEOUT = config.getint('session', 'hot_timeout')
COLD_TIMEOUT = config.getint('session', 'cold_timeout')
CLEANUP_INTERVAL = config.getint('session', 'cleanup_interval')
SESSIONS_DIR = config.get('DEFAULT', 'sessions_dir')

os.makedirs(SESSIONS_DIR, exist_ok=True)

_hot: Dict[str, Tuple[dict, float]] = {}
_hot_heap: list = []
_cold_heap: list = []

_lock = threading.Lock()
_stop = False

def _cold_path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")

def get_session(session_id: str, user_id: Optional[int] = None) -> dict:
    with _lock:
        now = time.time()
        if session_id in _hot:
            state, _ = _hot[session_id]
            # Migrate old format if necessary
            if "active_trees" not in state:
                state["active_trees"] = {}
            if "topics" not in state:
                state["topics"] = {}
            # If old group_id/path exist, convert to active_trees
            if "group_id" in state and state["group_id"] is not None:
                gid = state["group_id"]
                path = state.get("path", [])
                state["active_trees"][gid] = {"path": path, "last_used": now}
                del state["group_id"]
                if "path" in state:
                    del state["path"]
            _hot[session_id] = (state, now)
            heapq.heappush(_hot_heap, (now, session_id))
            return state

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
                with _lock:
                    _hot[session_id] = (state, now)
                    heapq.heappush(_hot_heap, (now, session_id))
                os.remove(cold_file)
                return state
            else:
                os.remove(cold_file)
        except Exception:
            pass

    new_state = {"topics": {}, "active_trees": {}}
    if user_id is not None:
        new_state["user_id"] = user_id
    with _lock:
        _hot[session_id] = (new_state, time.time())
        heapq.heappush(_hot_heap, (time.time(), session_id))
    return new_state

def save_session(session_id: str, state: dict) -> None:
    with _lock:
        now = time.time()
        # Ensure required keys exist
        if "active_trees" not in state:
            state["active_trees"] = {}
        if "topics" not in state:
            state["topics"] = {}
        if session_id in _hot:
            _hot[session_id] = (state, now)
            heapq.heappush(_hot_heap, (now, session_id))
        else:
            _hot[session_id] = (state, now)
            heapq.heappush(_hot_heap, (now, session_id))

def _cleanup():
    while not _stop:
        time.sleep(CLEANUP_INTERVAL)
        now = time.time()

        with _lock:
            while _hot_heap:
                ts, sid = _hot_heap[0]
                if sid not in _hot:
                    heapq.heappop(_hot_heap)
                    continue
                state, last_used = _hot[sid]
                if ts != last_used:
                    heapq.heappop(_hot_heap)
                    continue
                if now - last_used > HOT_TIMEOUT:
                    heapq.heappop(_hot_heap)
                    del _hot[sid]
                    cold_file = _cold_path(sid)
                    try:
                        with open(cold_file, 'w') as f:
                            json.dump({"state": state, "saved_at": last_used}, f)
                        heapq.heappush(_cold_heap, (last_used, sid))
                    except Exception:
                        pass
                else:
                    break

            while _cold_heap:
                saved_at, sid = _cold_heap[0]
                cold_file = _cold_path(sid)
                if not os.path.exists(cold_file):
                    heapq.heappop(_cold_heap)
                    continue
                if now - saved_at > COLD_TIMEOUT:
                    heapq.heappop(_cold_heap)
                    try:
                        os.remove(cold_file)
                    except Exception:
                        pass
                else:
                    break

_cleaner_thread = threading.Thread(target=_cleanup, daemon=True)
_cleaner_thread.start()

def stop_cleaner():
    global _stop
    _stop = True