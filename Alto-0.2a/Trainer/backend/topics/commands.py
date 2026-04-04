from typing import Optional, Dict, List
from ..model import get_model

def cmd_get_topics(name: str, **kwargs) -> List[str]:
    try:
        model = get_model(name)
        return model.get_topics()
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
        return {"status": "ok", "topics": model.get_topics()}
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
        return {"status": "ok", "topics": model.get_topics()}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_topic(name: str, topic: str, action: str = "reassign",
                     target: Optional[str] = None, **kwargs) -> Dict:
    try:
        model = get_model(name)
        model.delete_topic(topic, action, target)
        return {"status": "ok", "topics": model.get_topics()}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_topic_groups(name: str, topic: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        groups = model.get_topic_groups(topic)
        return {"groups": groups}
    except Exception as e:
        return {"error": str(e)}