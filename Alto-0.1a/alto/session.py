# session.py
_session_store = {}  # session_id -> state dict

def get_session(session_id: str) -> dict:
    """Retrieve state for a session, or create empty."""
    return _session_store.setdefault(session_id, {})

def save_session(session_id: str, state: dict) -> None:
    """Store updated state."""
    _session_store[session_id] = state