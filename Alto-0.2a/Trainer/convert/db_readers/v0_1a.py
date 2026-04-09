"""
Reader for Alto 0.1a legacy databases.
"""
import datetime
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

import msgpack

from .base import DatabaseReader
from ..icf_writer import ICFWriter


def unpack_msgpack(data: bytes) -> list:
    return msgpack.unpackb(data, raw=False)


class ReaderV0_1a(DatabaseReader):
    VERSION = "0.1a"

    def get_version(self) -> str:
        return self.VERSION

    def export_to_icf(self, db_path: Path, output_icf_dir: Path, batch_size: int = 100) -> Dict[str, int]:
        conn = self._open_connection(db_path)

        # Ensure model_info exists (some old dbs may lack it)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model_info'")
        if not cur.fetchone():
            # Use defaults
            meta = {
                "model_name": db_path.stem,
                "description": "",
                "author": "",
                "version": "1.0.0",
                "alto_version": "0.1a",
                "created_at": datetime.datetime.now().isoformat(),
                "updated_at": datetime.datetime.now().isoformat(),
            }
        else:
            cur = conn.execute("SELECT name, description, author, version, alto_version, created_at, updated_at FROM model_info")
            row = cur.fetchone()
            meta = {
                "model_name": row[0],
                "description": row[1] or "",
                "author": row[2] or "",
                "version": row[3] or "1.0.0",
                "alto_version": row[4] or "0.1a",
                "created_at": row[5],
                "updated_at": row[6],
            }

        writer = ICFWriter(output_icf_dir, batch_size)

        # Sections
        cur = conn.execute("SELECT id, name, sort_order FROM sections ORDER BY sort_order")
        sections = [{"id": r[0], "name": r[1], "sort_order": r[2]} for r in cur]
        writer.write_sections(sections)
        section_count = len(sections)

        # Topics
        cur = conn.execute("""
            SELECT t.id, t.name, COALESCE(s.name, '') as section
            FROM topics t
            LEFT JOIN sections s ON t.section_id = s.id
            ORDER BY t.id
        """)
        topics = [{"id": r[0], "name": r[1], "section": r[2]} for r in cur]
        writer.write_topics(topics)
        topic_count = len(topics)

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
        writer.write_variants(variants)
        variant_count = len(variants)

        # Groups (with follow‑up trees)
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
            # Questions (stored as blob in 0.1a)
            qcur = conn.execute("SELECT questions_blob FROM groups WHERE id = ?", (gid,))
            questions_blob = qcur.fetchone()[0]
            questions = unpack_msgpack(questions_blob)

            # Answers (stored as blob)
            acur = conn.execute("SELECT answers_blob FROM groups WHERE id = ?", (gid,))
            answers_blob = acur.fetchone()[0]
            answers = unpack_msgpack(answers_blob)

            # Follow‑up tree
            def build_tree(parent: Optional[int] = None) -> List[Dict]:
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

        writer.write_groups(groups)
        group_count = len(groups)

        # Fallbacks (none in 0.1a)
        writer.write_fallbacks([])

        conn.close()
        writer.finalize(meta)

        return {
            "sections": section_count,
            "topics": topic_count,
            "variants": variant_count,
            "groups": group_count,
            "fallbacks": 0,
        }