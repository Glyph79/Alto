import json
import os
import datetime
from typing import List, Dict, Optional, Any

class Trainer:
    def __init__(self, models_folder: str = "models"):
        self.models_folder = models_folder
        os.makedirs(self.models_folder, exist_ok=True)

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------
    def list_models(self) -> List[str]:
        models = []
        for f in os.listdir(self.models_folder):
            if f.endswith('.json'):
                models.append(f[:-5])
        return sorted(models)

    def get_model_path(self, name: str) -> str:
        return os.path.join(self.models_folder, f"{name}.json")

    def create_model(self, name: str, description: str = "", author: str = "", version: str = "1.0.0") -> Dict:
        if not name.strip():
            raise ValueError("Model name cannot be empty")
        if name in self.list_models():
            raise ValueError(f"Model '{name}' already exists")
        model_data = {
            "name": name,
            "description": description,
            "author": author,
            "version": version,
            "created_at": datetime.datetime.now().isoformat(),
            "sections": ["General", "Technical", "Creative"],
            "qa_groups": []
        }
        with open(self.get_model_path(name), "w", encoding="utf-8") as f:
            json.dump(model_data, f, indent=2)
        return model_data

    def load_model(self, name: str) -> Dict:
        path = self.get_model_path(name)
        if not os.path.exists(path):
            raise ValueError(f"Model '{name}' not found")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "sections" not in data:
            data["sections"] = ["General", "Technical", "Creative"]
        if "qa_groups" not in data:
            data["qa_groups"] = []
        return data

    def update_model_info(self, name: str, description: str = None, author: str = None, version: str = None) -> Dict:
        data = self.load_model(name)
        if description is not None:
            data["description"] = description
        if author is not None:
            data["author"] = author
        if version is not None:
            data["version"] = version
        data["updated_at"] = datetime.datetime.now().isoformat()
        with open(self.get_model_path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data

    def delete_model(self, name: str):
        path = self.get_model_path(name)
        if os.path.exists(path):
            os.remove(path)

    def save_model(self, name: str, qa_groups: List[Dict], sections: List[str] = None):
        data = self.load_model(name)
        data["qa_groups"] = qa_groups
        if sections is not None:
            data["sections"] = sections
        data["updated_at"] = datetime.datetime.now().isoformat()
        with open(self.get_model_path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ------------------------------------------------------------------
    # Section operations
    # ------------------------------------------------------------------
    def get_sections(self, model_name: str) -> List[str]:
        return self.load_model(model_name).get("sections", [])

    def add_section(self, model_name: str, section: str):
        data = self.load_model(model_name)
        if section not in data["sections"]:
            data["sections"].append(section)
            self.save_model(model_name, data["qa_groups"], data["sections"])

    def rename_section(self, model_name: str, old_name: str, new_name: str):
        data = self.load_model(model_name)
        if old_name not in data["sections"]:
            raise ValueError(f"Section '{old_name}' not found")
        if new_name in data["sections"] and new_name != old_name:
            raise ValueError(f"Section '{new_name}' already exists")
        idx = data["sections"].index(old_name)
        data["sections"][idx] = new_name
        for group in data["qa_groups"]:
            if group.get("section") == old_name:
                group["section"] = new_name
        self.save_model(model_name, data["qa_groups"], data["sections"])

    def delete_section(self, model_name: str, section: str, action: str = "uncategorized", target_section: str = None):
        data = self.load_model(model_name)
        if section not in data["sections"]:
            raise ValueError(f"Section '{section}' not found")
        groups_to_handle = [g for g in data["qa_groups"] if g.get("section") == section]
        if action == "uncategorized":
            for g in groups_to_handle:
                g["section"] = ""
        elif action == "delete":
            data["qa_groups"] = [g for g in data["qa_groups"] if g.get("section") != section]
        elif action == "move" and target_section:
            if target_section not in data["sections"] and target_section != section:
                raise ValueError(f"Target section '{target_section}' not found")
            for g in groups_to_handle:
                g["section"] = target_section
        data["sections"].remove(section)
        self.save_model(model_name, data["qa_groups"], data["sections"])

    # ------------------------------------------------------------------
    # Group operations
    # ------------------------------------------------------------------
    def get_groups(self, model_name: str, section_filter: str = None) -> List[Dict]:
        data = self.load_model(model_name)
        groups = data["qa_groups"]
        if section_filter == "All Sections":
            return groups
        if section_filter == "Uncategorized":
            return [g for g in groups if not g.get("section")]
        if section_filter:
            return [g for g in groups if g.get("section") == section_filter]
        return groups

    def add_group(self, model_name: str, group_data: Dict):
        data = self.load_model(model_name)
        if "group_name" not in group_data:
            group_data["group_name"] = "New Group"
        if "questions" not in group_data:
            group_data["questions"] = []
        if "answers" not in group_data:
            group_data["answers"] = []
        if "topic" not in group_data:
            group_data["topic"] = "general"
        if "priority" not in group_data:
            group_data["priority"] = "medium"
        if "section" not in group_data:
            group_data["section"] = data["sections"][0] if data["sections"] else ""
        if "follow_ups" not in group_data:
            group_data["follow_ups"] = []
        data["qa_groups"].append(group_data)
        self.save_model(model_name, data["qa_groups"], data["sections"])

    def update_group(self, model_name: str, index: int, group_data: Dict):
        data = self.load_model(model_name)
        if 0 <= index < len(data["qa_groups"]):
            data["qa_groups"][index].update(group_data)
            self.save_model(model_name, data["qa_groups"], data["sections"])
        else:
            raise IndexError("Group index out of range")

    def delete_group(self, model_name: str, index: int):
        data = self.load_model(model_name)
        if 0 <= index < len(data["qa_groups"]):
            del data["qa_groups"][index]
            self.save_model(model_name, data["qa_groups"], data["sections"])
        else:
            raise IndexError("Group index out of range")

    # ------------------------------------------------------------------
    # Question/Answer operations inside a group
    # ------------------------------------------------------------------
    def add_question(self, model_name: str, group_index: int, question: str):
        data = self.load_model(model_name)
        if 0 <= group_index < len(data["qa_groups"]):
            data["qa_groups"][group_index].setdefault("questions", []).append(question)
            self.save_model(model_name, data["qa_groups"], data["sections"])
        else:
            raise IndexError("Group index out of range")

    def update_question(self, model_name: str, group_index: int, q_index: int, new_question: str):
        data = self.load_model(model_name)
        group = data["qa_groups"][group_index]
        if 0 <= q_index < len(group.get("questions", [])):
            group["questions"][q_index] = new_question
            self.save_model(model_name, data["qa_groups"], data["sections"])
        else:
            raise IndexError("Question index out of range")

    def delete_question(self, model_name: str, group_index: int, q_index: int):
        data = self.load_model(model_name)
        group = data["qa_groups"][group_index]
        if 0 <= q_index < len(group.get("questions", [])):
            del group["questions"][q_index]
            self.save_model(model_name, data["qa_groups"], data["sections"])
        else:
            raise IndexError("Question index out of range")

    def add_answer(self, model_name: str, group_index: int, answer: str):
        data = self.load_model(model_name)
        if 0 <= group_index < len(data["qa_groups"]):
            data["qa_groups"][group_index].setdefault("answers", []).append(answer)
            self.save_model(model_name, data["qa_groups"], data["sections"])
        else:
            raise IndexError("Group index out of range")

    def update_answer(self, model_name: str, group_index: int, a_index: int, new_answer: str):
        data = self.load_model(model_name)
        group = data["qa_groups"][group_index]
        if 0 <= a_index < len(group.get("answers", [])):
            group["answers"][a_index] = new_answer
            self.save_model(model_name, data["qa_groups"], data["sections"])
        else:
            raise IndexError("Answer index out of range")

    def delete_answer(self, model_name: str, group_index: int, a_index: int):
        data = self.load_model(model_name)
        group = data["qa_groups"][group_index]
        if 0 <= a_index < len(group.get("answers", [])):
            del group["answers"][a_index]
            self.save_model(model_name, data["qa_groups"], data["sections"])
        else:
            raise IndexError("Answer index out of range")

    # ------------------------------------------------------------------
    # Follow-up trees
    # ------------------------------------------------------------------
    def get_followups(self, model_name: str, group_index: int) -> List:
        data = self.load_model(model_name)
        if 0 <= group_index < len(data["qa_groups"]):
            return data["qa_groups"][group_index].get("follow_ups", [])
        raise IndexError("Group index out of range")

    def save_followups(self, model_name: str, group_index: int, follow_ups: List):
        data = self.load_model(model_name)
        if 0 <= group_index < len(data["qa_groups"]):
            data["qa_groups"][group_index]["follow_ups"] = follow_ups
            self.save_model(model_name, data["qa_groups"], data["sections"])
        else:
            raise IndexError("Group index out of range")

    # ------------------------------------------------------------------
    # Import/Export
    # ------------------------------------------------------------------
    def import_json(self, model_name: str, filepath: str) -> int:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "qa_groups" in data:
            groups = data["qa_groups"]
        elif isinstance(data, list):
            groups = data
        else:
            groups = [data]
        current = self.load_model(model_name)
        current["qa_groups"].extend(groups)
        self.save_model(model_name, current["qa_groups"], current["sections"])
        return len(groups)

    def export_json(self, model_name: str, full: bool = True) -> Dict:
        return self.load_model(model_name)