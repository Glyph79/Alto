from typing import Optional, Dict
from train.model import get_model

def cmd_add_section(name: str, section: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        # Check if section already exists
        if section in model.get_sections():
            return {"error": "Section already exists"}
        model.add_section(section)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_rename_section(name: str, old: str, new: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        if old not in model.get_sections():
            return {"error": f"Section '{old}' not found"}
        if new in model.get_sections() and new != old:
            return {"error": f"Section '{new}' already exists"}
        model.rename_section(old, new)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_section(name: str, section: str, action: str = "uncategorized",
                       target: Optional[str] = None, **kwargs) -> Dict:
    try:
        model = get_model(name)
        model.delete_section(section, action, target)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}