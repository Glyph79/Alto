import json
from pathlib import Path
from typing import Dict, List

from backend.models.commands import cmd_create_model
from backend.model import get_model
from backend.utils.file_helpers import list_all_models, get_model_container_path

def import_icf(icf_dir: Path, new_model_name: str, models_dir: Path, create_missing: bool = True) -> str:
    models_dir = Path(models_dir).resolve()
    icf_dir = Path(icf_dir)
    if not icf_dir.is_dir():
        raise ValueError(f"Not a directory: {icf_dir}")
    manifest_path = icf_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Missing manifest.json in {icf_dir}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    existing = [m["name"] for m in list_all_models()]
    if new_model_name in existing:
        raise RuntimeError(f"Model '{new_model_name}' already exists.")

    result = cmd_create_model(name=new_model_name,
                              description=manifest.get("description", ""),
                              author=manifest.get("author", ""),
                              version=manifest.get("version", "1.0.0"))
    if "error" in result:
        raise RuntimeError(f"Failed to create model: {result['error']}")

    model = get_model(new_model_name)

    def read_batches(entity_type: str) -> List[Dict]:
        entity_dir = icf_dir / entity_type
        if not entity_dir.is_dir():
            return []
        items = []
        for batch_file in sorted(entity_dir.glob(f"{entity_type}_*.json")):
            with open(batch_file, "r", encoding="utf-8") as f:
                batch = json.load(f)
                if isinstance(batch, list):
                    items.extend(batch)
                else:
                    items.append(batch)
        return items

    sections = read_batches("sections")
    for sec in sections:
        name = sec["name"]
        if name == "Uncategorized":
            continue
        try:
            model.add_section(name)
        except Exception as e:
            if "already exists" not in str(e):
                print(f"  Warning: could not add section '{name}': {e}")
    print(f"  Imported {len(sections)} sections")

    topics = read_batches("topics")
    for topic in topics:
        name = topic["name"]
        section_name = topic.get("section", "")
        try:
            model.add_topic(name, section_name if section_name else None)
        except Exception as e:
            if "already exists" not in str(e):
                print(f"  Warning: could not add topic '{name}': {e}")
    print(f"  Imported {len(topics)} topics")

    variants = read_batches("variants")
    for variant in variants:
        name = variant["name"]
        section_name = variant.get("section", "")
        words = variant.get("words", [])
        try:
            model.add_variant(name, section_name if section_name else None, words)
        except Exception as e:
            print(f"  Warning: could not add variant '{name}': {e}")
    print(f"  Imported {len(variants)} variants")

    groups = read_batches("groups")
    for group in groups:
        group_dict = {
            "group_name": group["group_name"],
            "topic": group.get("topic", ""),
            "section": group.get("section", ""),
            "fallback": group.get("fallback", ""),
            "questions": group.get("questions", []),
            "answers": group.get("answers", []),
            "follow_ups": group.get("follow_ups", [])
        }
        try:
            model.insert_group(group_dict)
        except Exception as e:
            print(f"  Warning: could not add group '{group['group_name']}': {e}")
    print(f"  Imported {len(groups)} groups")

    fallbacks = read_batches("fallbacks")
    for fb in fallbacks:
        name = fb["name"]
        description = fb.get("description", "")
        answers = fb.get("answers", [])
        try:
            model.create_fallback(name, description, answers)
        except Exception as e:
            print(f"  Warning: could not add fallback '{name}': {e}")
    print(f"  Imported {len(fallbacks)} fallbacks")

    model.close_and_repack()
    container_path = get_model_container_path(new_model_name)
    return str(container_path)