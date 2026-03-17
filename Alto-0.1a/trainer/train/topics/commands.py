"""Commands for topic management."""
import json
from typing import Optional, Dict, List
from train.model import get_model

def cmd_get_topics(name: str, **kwargs) -> List[str]:
    try:
        model = get_model(name)
        return model.get_topics()
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_add_topic(name: str, topic: str, **kwargs) -> Dict:
    if topic.lower() == "null":
        return {"error": "Topic name cannot be 'null'"}
    try:
        model = get_model(name)
        topics = model.get_topics()
        if topic in topics:
            return {"error": "Topic already exists"}
        topics.append(topic)
        model.update_topics(topics)
        return {"status": "ok", "topics": topics}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_rename_topic(name: str, old: str, new: str, **kwargs) -> Dict:
    if new.lower() == "null":
        return {"error": "Topic name cannot be 'null'"}
    try:
        model = get_model(name)
        topics = model.get_topics()
        if old not in topics:
            return {"error": f"Topic '{old}' not found"}
        if new in topics and new != old:
            return {"error": f"Topic '{new}' already exists"}
        # Rename in topics list
        idx = topics.index(old)
        topics[idx] = new
        model.update_topics(topics)
        # Update all groups that used the old topic
        summaries = model.get_group_summaries()
        for s in summaries:
            if s["topic"] == old:
                group = model.get_group_by_id(s["id"])
                group["topic"] = new
                model.update_group(s["id"], group)
        return {"status": "ok", "topics": topics}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_topic(name: str, topic: str, action: str = "reassign",
                     target: Optional[str] = None, **kwargs) -> Dict:
    try:
        model = get_model(name)
        topics = model.get_topics()
        if topic not in topics:
            return {"error": f"Topic '{topic}' not found"}

        # Find groups using this topic
        summaries = model.get_group_summaries()
        groups_to_update = [s for s in summaries if s["topic"] == topic]

        if action == "reassign":
            # target can be empty string (meaning no topic) or a valid topic
            if target is None:
                target = ""   # default to no topic
            if target != "" and target not in topics:
                return {"error": f"Target topic '{target}' not found"}
            # Move groups to target topic
            for s in groups_to_update:
                group = model.get_group_by_id(s["id"])
                group["topic"] = target
                model.update_group(s["id"], group)
        elif action == "delete_groups":
            # Delete all groups using this topic
            for s in groups_to_update:
                model.delete_group(s["id"])
        else:
            return {"error": f"Invalid action: {action}"}

        # Remove topic from list
        topics.remove(topic)
        model.update_topics(topics)
        return {"status": "ok", "topics": topics}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}

def cmd_get_topic_groups(name: str, topic: str, **kwargs) -> Dict:
    """Return lightweight summaries of groups that have the given topic."""
    try:
        model = get_model(name)
        # Get all group summaries with counts
        all_summaries = model.get_group_summaries_with_counts()
        # Filter by topic
        topic_groups = [g for g in all_summaries if g.get("topic") == topic]
        return {"groups": topic_groups}
    except FileNotFoundError:
        return {"error": f"Model '{name}' not found"}
    except Exception as e:
        return {"error": str(e)}