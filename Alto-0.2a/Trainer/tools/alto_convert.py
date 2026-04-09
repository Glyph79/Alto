#!/usr/bin/env python3
"""
Alto Model Converter: v0.1 ↔ ICF (internal) ↔ v0.2a

Internal commands (used by Trainer backend):
    export-db --input-db <file.db> --output-icf <dir.icf> --batch-size N
    import-icf --input-icf <dir.icf> --output-model <name> --models-dir PATH [--create-missing]
"""

import os
import sys
import json
import shutil
import sqlite3
import tempfile
import argparse
import datetime
from pathlib import Path

# ----------------------------------------------------------------------
# Ensure we can import Trainer's backend modules
# ----------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
TRAINER_DIR = SCRIPT_DIR.parent
if str(TRAINER_DIR) not in sys.path:
    sys.path.insert(0, str(TRAINER_DIR))

import msgpack
from backend.models.commands import cmd_create_model
from backend.model import get_model                     # re‑exported from schema
from backend.utils.file_helpers import list_all_models, get_model_container_path, read_manifest

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
ICF_FORMAT_VERSION = "1.0"

# ----------------------------------------------------------------------
# Helper to unpack msgpack (same as v0.1a adapter)
# ----------------------------------------------------------------------
def unpack_msgpack(data):
    return msgpack.unpackb(data, raw=False)

# ----------------------------------------------------------------------
# Export: legacy .db file → ICF directory
# ----------------------------------------------------------------------
def export_db_file(db_path, output_path, batch_size):
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # Ensure model_info exists (legacy files may lack it)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model_info'")
    if not cur.fetchone():
        conn.execute("""
            CREATE TABLE model_info (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                author TEXT NOT NULL,
                version TEXT NOT NULL,
                alto_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        now = datetime.datetime.now().isoformat()
        conn.execute(
            "INSERT INTO model_info (name, description, author, version, alto_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (db_path.stem, "", "", "1.0.0", "0.1a", now, now)
        )
        conn.commit()

    # Metadata
    cur = conn.execute("SELECT name, description, author, version, alto_version, created_at, updated_at FROM model_info")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Model info not found")
    meta = {
        "format_version": ICF_FORMAT_VERSION,
        "model_name": row[0],
        "description": row[1] or "",
        "author": row[2] or "",
        "version": row[3] or "1.0.0",
        "alto_version": row[4] or "0.1a",
        "created_at": row[5],
        "updated_at": row[6],
    }

    out_dir = Path(output_path)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    def write_batches(entity_type, items):
        if not items:
            return 0
        entity_dir = out_dir / entity_type
        entity_dir.mkdir(exist_ok=True)
        total = len(items)
        batch_idx = 1
        for i in range(0, total, batch_size):
            batch = items[i:i+batch_size]
            filename = f"{entity_type}_{batch_idx:04d}.json"
            with open(entity_dir / filename, "w", encoding="utf-8") as f:
                json.dump(batch, f, indent=2, ensure_ascii=False)
            batch_idx += 1
        return total

    # Sections
    cur = conn.execute("SELECT id, name, sort_order FROM sections ORDER BY sort_order")
    sections = [{"id": r[0], "name": r[1], "sort_order": r[2]} for r in cur]
    meta["section_count"] = write_batches("sections", sections)

    # Topics
    cur = conn.execute("""
        SELECT t.id, t.name, COALESCE(s.name, '') as section
        FROM topics t
        LEFT JOIN sections s ON t.section_id = s.id
        ORDER BY t.id
    """)
    topics = [{"id": r[0], "name": r[1], "section": r[2]} for r in cur]
    meta["topic_count"] = write_batches("topics", topics)

    # Variants
    cur = conn.execute("""
        SELECT vg.id, vg.name, COALESCE(s.name, '') as section,
               GROUP_CONCAT(vw.word, ',') as words
        FROM variant_groups vg
        LEFT JOIN sections s ON vg.section_id = s.id
        LEFT JOIN variant_words vw ON vw.group_id = vg.id
        GROUP BY vg.id
        ORDER BY vg.id
    """)
    variants = []
    for r in cur:
        words = r[3].split(',') if r[3] else []
        variants.append({"id": r[0], "name": r[1], "section": r[2], "words": words})
    meta["variant_count"] = write_batches("variants", variants)

    # Groups
    cur = conn.execute("""
        SELECT g.id, g.group_name,
               COALESCE(t.name, '') as topic,
               COALESCE(s.name, '') as section
        FROM groups g
        LEFT JOIN topics t ON g.topic_id = t.id
        LEFT JOIN sections s ON g.section_id = s.id
        ORDER BY g.id
    """)
    groups = []
    for row in cur:
        gid = row[0]
        # Questions
        qcur = conn.execute("""
            SELECT q.text FROM group_questions gq
            JOIN questions q ON gq.question_id = q.id
            WHERE gq.group_id = ?
            ORDER BY gq.sort_order
        """, (gid,))
        questions = [r[0] for r in qcur]
        # Answers
        acur = conn.execute("SELECT answers_blob FROM groups WHERE id = ?", (gid,))
        answers_blob = acur.fetchone()[0]
        answers = unpack_msgpack(answers_blob)
        # Follow‑up tree
        def build_tree(parent=None):
            nodes = []
            cur = conn.execute("""
                SELECT id, branch_name, questions_blob, answers_blob
                FROM followup_nodes
                WHERE group_id = ? AND parent_id IS ?
                ORDER BY id
            """, (gid, parent))
            for nr in cur:
                node = {
                    "branch_name": nr[1],
                    "questions": unpack_msgpack(nr[2]),
                    "answers": unpack_msgpack(nr[3]),
                    "fallback": "",
                    "children": build_tree(nr[0])
                }
                nodes.append(node)
            return nodes
        follow_ups = build_tree()
        groups.append({
            "id": gid,
            "group_name": row[1],
            "topic": row[2],
            "section": row[3],
            "fallback": "",
            "questions": questions,
            "answers": answers,
            "follow_ups": follow_ups
        })
    meta["group_count"] = write_batches("groups", groups)

    # Fallbacks are absent in v0.1a – create empty batch directory
    fallbacks_dir = out_dir / "fallbacks"
    fallbacks_dir.mkdir(exist_ok=True)
    with open(fallbacks_dir / "fallbacks_0001.json", "w", encoding="utf-8") as f:
        json.dump([], f)
    meta["fallback_count"] = 0

    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    conn.close()
    print(f"Export complete: {out_dir}")
    print(f"  Sections: {meta['section_count']}, Topics: {meta['topic_count']}, Variants: {meta['variant_count']}, Groups: {meta['group_count']}")

# ----------------------------------------------------------------------
# Import: ICF directory → v0.2a model (uses Trainer's model API)
# ----------------------------------------------------------------------
def import_icf(icf_path, new_model_name, models_dir, create_missing=False):
    models_dir = Path(models_dir).resolve()
    icf_dir = Path(icf_path)
    if not icf_dir.is_dir():
        raise ValueError(f"Not a directory: {icf_path}")
    manifest_path = icf_dir / "manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Missing manifest.json in {icf_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if manifest.get("format_version") != ICF_FORMAT_VERSION:
        print(f"Warning: Expected version {ICF_FORMAT_VERSION}, got {manifest.get('format_version')}")

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

    def read_batches(entity_type):
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

    # Sections
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

    # Topics
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

    # Variants
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

    # Groups
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

    model.close_and_repack()
    print(f"Import complete. New model '{new_model_name}' created at {models_dir}")

# ----------------------------------------------------------------------
# CLI (internal)
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Alto Model Converter (internal)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    expdb = subparsers.add_parser("export-db")
    expdb.add_argument("--input-db", required=True)
    expdb.add_argument("--output-icf", required=True)
    expdb.add_argument("--batch-size", type=int, default=100)

    imp = subparsers.add_parser("import-icf")
    imp.add_argument("--input-icf", required=True)
    imp.add_argument("--output-model", required=True)
    imp.add_argument("--models-dir", default=str(TRAINER_DIR / "models"))
    imp.add_argument("--create-missing", action="store_true")

    args = parser.parse_args()

    try:
        if args.command == "export-db":
            export_db_file(args.input_db, args.output_icf, args.batch_size)
        elif args.command == "import-icf":
            import_icf(args.input_icf, args.output_model, args.models_dir, args.create_missing)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()