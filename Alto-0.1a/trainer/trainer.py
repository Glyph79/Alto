import json
import os
import datetime
from typing import List, Dict

class Trainer:
    def __init__(self, models_folder: str = "models"):
        self.models_folder = models_folder
        os.makedirs(self.models_folder, exist_ok=True)

    # ------------------------------------------------------------------
    # Compact ↔ Full conversion (internal)
    # ------------------------------------------------------------------
    def _expand_followups(self, compact_followups: List) -> List:
        expanded = []
        for node in compact_followups:
            expanded.append({
                "branch_name": node.get("n", ""),
                "questions": node.get("q", []),
                "answers": node.get("a", []),
                "children": self._expand_followups(node.get("c", []))
            })
        return expanded

    def _compact_followups(self, full_followups: List) -> List:
        compact = []
        for node in full_followups:
            compact.append({
                "n": node.get("branch_name", ""),
                "q": node.get("questions", []),
                "a": node.get("answers", []),
                "c": self._compact_followups(node.get("children", []))
            })
        return compact

    def _expand_model(self, compact: Dict) -> Dict:
        return {
            "name": compact.get("n", ""),
            "description": compact.get("d", ""),
            "author": compact.get("a", ""),
            "version": compact.get("v", "1.0.0"),
            "created_at": compact.get("c", ""),
            "updated_at": compact.get("u", ""),
            "sections": compact.get("s", ["General", "Technical", "Creative"]),
            "qa_groups": [
                {
                    "group_name": g.get("n", ""),
                    "group_description": g.get("d", ""),
                    "questions": g.get("q", []),
                    "answers": g.get("a", []),
                    "topic": g.get("t", "general"),
                    "priority": g.get("p", "medium"),
                    "section": g.get("sec", ""),
                    "follow_ups": self._expand_followups(g.get("f", []))
                }
                for g in compact.get("g", [])
            ]
        }

    def _compact_model(self, full: Dict) -> Dict:
        return {
            "n": full.get("name", ""),
            "d": full.get("description", ""),
            "a": full.get("author", ""),
            "v": full.get("version", "1.0.0"),
            "c": full.get("created_at", ""),
            "u": full.get("updated_at", ""),
            "s": full.get("sections", ["General", "Technical", "Creative"]),
            "g": [
                {
                    "n": g.get("group_name", ""),
                    "d": g.get("group_description", ""),
                    "q": g.get("questions", []),
                    "a": g.get("answers", []),
                    "t": g.get("topic", "general"),
                    "p": g.get("priority", "medium"),
                    "sec": g.get("section", ""),
                    "f": self._compact_followups(g.get("follow_ups", []))
                }
                for g in full.get("qa_groups", [])
            ]
        }

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
        now = datetime.datetime.now().isoformat()
        compact = {
            "n": name,
            "d": description,
            "a": author,
            "v": version,
            "c": now,
            "s": ["General", "Technical", "Creative"],
            "g": []
        }
        with open(self.get_model_path(name), "w", encoding="utf-8") as f:
            json.dump(compact, f, separators=(',', ':'))
        return self._expand_model(compact)

    def load_model(self, name: str) -> Dict:
        path = self.get_model_path(name)
        if not os.path.exists(path):
            raise ValueError(f"Model '{name}' not found")
        with open(path, "r", encoding="utf-8") as f:
            compact = json.load(f)
        return self._expand_model(compact)

    def update_model_info(self, name: str, description: str = None, author: str = None, version: str = None) -> Dict:
        full = self.load_model(name)
        if description is not None:
            full["description"] = description
        if author is not None:
            full["author"] = author
        if version is not None:
            full["version"] = version
        full["updated_at"] = datetime.datetime.now().isoformat()
        compact = self._compact_model(full)
        with open(self.get_model_path(name), "w", encoding="utf-8") as f:
            json.dump(compact, f, separators=(',', ':'))
        return full

    def delete_model(self, name: str):
        path = self.get_model_path(name)
        if os.path.exists(path):
            os.remove(path)

    def save_model(self, name: str, qa_groups: List[Dict], sections: List[str] = None):
        full = self.load_model(name)
        full["qa_groups"] = qa_groups
        if sections is not None:
            full["sections"] = sections
        full["updated_at"] = datetime.datetime.now().isoformat()
        compact = self._compact_model(full)
        with open(self.get_model_path(name), "w", encoding="utf-8") as f:
            json.dump(compact, f, separators=(',', ':'))

    # ------------------------------------------------------------------
    # Section operations
    # ------------------------------------------------------------------
    def get_sections(self, model_name: str) -> List[str]:
        return self.load_model(model_name).get("sections", [])

    def add_section(self, model_name: str, section: str):
        full = self.load_model(model_name)
        if section not in full["sections"]:
            full["sections"].append(section)
            self.save_model(model_name, full["qa_groups"], full["sections"])

    def rename_section(self, model_name: str, old_name: str, new_name: str):
        full = self.load_model(model_name)
        if old_name not in full["sections"]:
            raise ValueError(f"Section '{old_name}' not found")
        if new_name in full["sections"] and new_name != old_name:
            raise ValueError(f"Section '{new_name}' already exists")
        idx = full["sections"].index(old_name)
        full["sections"][idx] = new_name
        for group in full["qa_groups"]:
            if group.get("section") == old_name:
                group["section"] = new_name
        self.save_model(model_name, full["qa_groups"], full["sections"])

    def delete_section(self, model_name: str, section: str, action: str = "uncategorized", target_section: str = None):
        full = self.load_model(model_name)
        if section not in full["sections"]:
            raise ValueError(f"Section '{section}' not found")
        groups_to_handle = [g for g in full["qa_groups"] if g.get("section") == section]
        if action == "uncategorized":
            for g in groups_to_handle:
                g["section"] = ""
        elif action == "delete":
            full["qa_groups"] = [g for g in full["qa_groups"] if g.get("section") != section]
        elif action == "move" and target_section:
            if target_section not in full["sections"] and target_section != section:
                raise ValueError(f"Target section '{target_section}' not found")
            for g in groups_to_handle:
                g["section"] = target_section
        full["sections"].remove(section)
        self.save_model(model_name, full["qa_groups"], full["sections"])

    # ------------------------------------------------------------------
    # Group operations
    # ------------------------------------------------------------------
    def get_groups(self, model_name: str, section_filter: str = None) -> List[Dict]:
        full = self.load_model(model_name)
        groups = full["qa_groups"]
        if section_filter == "All Sections":
            return groups
        if section_filter == "Uncategorized":
            return [g for g in groups if not g.get("section")]
        if section_filter:
            return [g for g in groups if g.get("section") == section_filter]
        return groups

    def add_group(self, model_name: str, group_data: Dict):
        full = self.load_model(model_name)
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
            group_data["section"] = full["sections"][0] if full["sections"] else ""
        if "follow_ups" not in group_data:
            group_data["follow_ups"] = []
        full["qa_groups"].append(group_data)
        self.save_model(model_name, full["qa_groups"], full["sections"])

    def update_group(self, model_name: str, index: int, group_data: Dict):
        full = self.load_model(model_name)
        if 0 <= index < len(full["qa_groups"]):
            full["qa_groups"][index].update(group_data)
            self.save_model(model_name, full["qa_groups"], full["sections"])
        else:
            raise IndexError("Group index out of range")

    def delete_group(self, model_name: str, index: int):
        full = self.load_model(model_name)
        if 0 <= index < len(full["qa_groups"]):
            del full["qa_groups"][index]
            self.save_model(model_name, full["qa_groups"], full["sections"])
        else:
            raise IndexError("Group index out of range")

    # ------------------------------------------------------------------
    # Question/Answer operations inside a group
    # ------------------------------------------------------------------
    def add_question(self, model_name: str, group_index: int, question: str):
        full = self.load_model(model_name)
        if 0 <= group_index < len(full["qa_groups"]):
            full["qa_groups"][group_index].setdefault("questions", []).append(question)
            self.save_model(model_name, full["qa_groups"], full["sections"])
        else:
            raise IndexError("Group index out of range")

    def update_question(self, model_name: str, group_index: int, q_index: int, new_question: str):
        full = self.load_model(model_name)
        group = full["qa_groups"][group_index]
        if 0 <= q_index < len(group.get("questions", [])):
            group["questions"][q_index] = new_question
            self.save_model(model_name, full["qa_groups"], full["sections"])
        else:
            raise IndexError("Question index out of range")

    def delete_question(self, model_name: str, group_index: int, q_index: int):
        full = self.load_model(model_name)
        group = full["qa_groups"][group_index]
        if 0 <= q_index < len(group.get("questions", [])):
            del group["questions"][q_index]
            self.save_model(model_name, full["qa_groups"], full["sections"])
        else:
            raise IndexError("Question index out of range")

    def add_answer(self, model_name: str, group_index: int, answer: str):
        full = self.load_model(model_name)
        if 0 <= group_index < len(full["qa_groups"]):
            full["qa_groups"][group_index].setdefault("answers", []).append(answer)
            self.save_model(model_name, full["qa_groups"], full["sections"])
        else:
            raise IndexError("Group index out of range")

    def update_answer(self, model_name: str, group_index: int, a_index: int, new_answer: str):
        full = self.load_model(model_name)
        group = full["qa_groups"][group_index]
        if 0 <= a_index < len(group.get("answers", [])):
            group["answers"][a_index] = new_answer
            self.save_model(model_name, full["qa_groups"], full["sections"])
        else:
            raise IndexError("Answer index out of range")

    def delete_answer(self, model_name: str, group_index: int, a_index: int):
        full = self.load_model(model_name)
        group = full["qa_groups"][group_index]
        if 0 <= a_index < len(group.get("answers", [])):
            del group["answers"][a_index]
            self.save_model(model_name, full["qa_groups"], full["sections"])
        else:
            raise IndexError("Answer index out of range")

    # ------------------------------------------------------------------
    # Follow-up trees
    # ------------------------------------------------------------------
    def get_followups(self, model_name: str, group_index: int) -> List:
        full = self.load_model(model_name)
        if 0 <= group_index < len(full["qa_groups"]):
            return full["qa_groups"][group_index].get("follow_ups", [])
        raise IndexError("Group index out of range")

    def save_followups(self, model_name: str, group_index: int, follow_ups: List):
        full = self.load_model(model_name)
        if 0 <= group_index < len(full["qa_groups"]):
            full["qa_groups"][group_index]["follow_ups"] = follow_ups
            self.save_model(model_name, full["qa_groups"], full["sections"])
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
        elif isinstance(data, dict) and "g" in data:
            expanded = self._expand_model(data)
            groups = expanded["qa_groups"]
        elif isinstance(data, list):
            groups = data
        else:
            groups = [data]
        current = self.load_model(model_name)
        current["qa_groups"].extend(groups)
        self.save_model(model_name, current["qa_groups"], current["sections"])
        return len(groups)

    def export_json(self, model_name: str, full: bool = True) -> Dict:
        if full:
            return self.load_model(model_name)
        else:
            return self._compact_model(self.load_model(model_name))
