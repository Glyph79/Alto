from typing import Optional, Dict, List
from ..model import get_model

def cmd_get_topics(name: str, limit: int = 20, offset: int = 0, **kwargs) -> Dict:
    try:
        model = get_model(name)
        topics, total = model.get_topics_paginated(limit, offset)
        return {"topics": topics, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        return {"error": str(e)}

def cmd_add_topic(name: str, topic: str, **kwargs) -> Dict:
    if topic.lower() == "null":
        return {"error": "Topic name cannot be 'null'"}
    try:
        model = get_model(name)
        if topic in model.get_topics():
            return {"error": "Topic already exists"}
        model.add_topic(topic)
        conn = model.conn
        cur = conn.execute("SELECT id, name FROM topics WHERE name = ?", (topic,))
        row = cur.fetchone()
        return {"status": "ok", "topic": {"id": row[0], "name": row[1]}, "topics": [{"id": r[0], "name": r[1]} for r in conn.execute("SELECT id, name FROM topics ORDER BY name")]}
    except Exception as e:
        return {"error": str(e)}

def cmd_rename_topic(name: str, old: str, new: str, **kwargs) -> Dict:
    if new.lower() == "null":
        return {"error": "Topic name cannot be 'null'"}
    try:
        model = get_model(name)
        if old not in model.get_topics():
            return {"error": f"Topic '{old}' not found"}
        if new in model.get_topics() and new != old:
            return {"error": f"Topic '{new}' already exists"}
        model.rename_topic(old, new)
        conn = model.conn
        return {"status": "ok", "topics": [{"id": r[0], "name": r[1]} for r in conn.execute("SELECT id, name FROM topics ORDER BY name")]}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_topic(name: str, topic: str, action: str = "reassign",
                     target: Optional[str] = None, **kwargs) -> Dict:
    try:
        model = get_model(name)
        model.delete_topic(topic, action, target)
        conn = model.conn
        return {"status": "ok", "topics": [{"id": r[0], "name": r[1]} for r in conn.execute("SELECT id, name FROM topics ORDER BY name")]}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_topic_groups(name: str, topic: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        groups = model.get_topic_groups(topic)
        return {"groups": groups}
    except Exception as e:
        return {"error": str(e)}