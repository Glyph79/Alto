# alto/core/model_info.py
import os
from typing import Dict, Any, Optional
from .adapters import get_adapter
from ..config import MODELS_DIR

def get_model_file_size(model_name: str) -> int:
    """Return file size in bytes of the model's container or legacy DB."""
    from .adapters.base import get_model_container_path, get_legacy_db_path
    path = get_model_container_path(model_name) or get_legacy_db_path(model_name)
    if path and os.path.exists(path):
        return os.path.getsize(path)
    return 0

def get_model_info(model_name: str) -> Optional[Dict[str, Any]]:
    """Retrieve detailed info about a model."""
    try:
        adapter = get_adapter(model_name)
        conn = adapter.get_connection(model_name)
    except Exception:
        return None

    # Count groups
    cur = conn.execute("SELECT COUNT(*) FROM groups")
    group_count = cur.fetchone()[0]

    # Count follow-up nodes
    cur = conn.execute("SELECT COUNT(*) FROM followup_nodes")
    node_count = cur.fetchone()[0]

    # Average follow-up tree size (nodes per group that have follow-ups)
    cur = conn.execute("""
        SELECT group_id, COUNT(*) as cnt
        FROM followup_nodes
        GROUP BY group_id
    """)
    counts = [row[1] for row in cur]
    avg_tree_size = sum(counts) / len(counts) if counts else 0

    # Count topics
    cur = conn.execute("SELECT COUNT(*) FROM topics")
    topic_count = cur.fetchone()[0]

    file_size = get_model_file_size(model_name)

    return {
        "name": model_name,
        "groups": group_count,
        "followup_nodes": node_count,
        "avg_tree_size": round(avg_tree_size, 2),
        "topics": topic_count,
        "file_size_bytes": file_size,
        "file_size_mb": round(file_size / (1024 * 1024), 2)
    }

def list_models() -> list:
    """Return list of available model names."""
    if not os.path.exists(MODELS_DIR):
        return []
    models = set()
    for entry in os.listdir(MODELS_DIR):
        if entry.endswith('.rbm'):
            models.add(entry[:-4])
        elif entry.endswith('.db'):
            models.add(entry[:-3])
        elif os.path.isdir(os.path.join(MODELS_DIR, entry)):
            # Check for .rbm inside folder
            for f in os.listdir(os.path.join(MODELS_DIR, entry)):
                if f.endswith('.rbm'):
                    models.add(f[:-4])
                elif f.endswith('.db'):
                    models.add(f[:-3])
    return sorted(models)