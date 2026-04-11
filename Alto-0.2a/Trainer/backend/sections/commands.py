from typing import Optional, Dict
from ..model import get_model

def cmd_get_sections(name: str, **kwargs):
    try:
        model = get_model(name)
        conn = model.conn
        cur = conn.execute("SELECT id, name FROM sections ORDER BY sort_order")
        sections = [{"id": row[0], "name": row[1]} for row in cur]
        return sections
    except Exception as e:
        return {"error": str(e)}

def cmd_add_section(name: str, section: str, **kwargs) -> Dict:
    try:
        model = get_model(name)
        if section in model.get_sections():
            return {"error": "Section already exists"}
        model.add_section(section)
        conn = model.conn
        cur = conn.execute("SELECT id, name FROM sections ORDER BY sort_order")
        sections = [{"id": row[0], "name": row[1]} for row in cur]
        return {"status": "ok", "sections": sections}
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
        conn = model.conn
        cur = conn.execute("SELECT id, name FROM sections ORDER BY sort_order")
        sections = [{"id": row[0], "name": row[1]} for row in cur]
        return {"status": "ok", "sections": sections}
    except Exception as e:
        return {"error": str(e)}

def cmd_delete_section(name: str, section: str, action: str = "uncategorized",
                       target: Optional[str] = None, **kwargs) -> Dict:
    try:
        model = get_model(name)
        model.delete_section(section, action, target)
        conn = model.conn
        cur = conn.execute("SELECT id, name FROM sections ORDER BY sort_order")
        sections = [{"id": row[0], "name": row[1]} for row in cur]
        return {"status": "ok", "sections": sections}
    except Exception as e:
        return {"error": str(e)}