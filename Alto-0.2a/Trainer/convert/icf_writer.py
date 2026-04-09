"""
Write batched JSON files in ICF format.
"""
import json
from pathlib import Path
from typing import Any, Dict, List


class ICFWriter:
    """Writes an ICF directory from data provided by a database reader."""

    def __init__(self, output_dir: Path, batch_size: int = 100):
        self.output_dir = output_dir
        self.batch_size = batch_size
        self._sections_written = 0
        self._topics_written = 0
        self._variants_written = 0
        self._groups_written = 0
        self._fallbacks_written = 0

        if output_dir.exists():
            import shutil
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True)

    def _write_batches(self, entity_type: str, items: List[Dict]) -> int:
        if not items:
            return 0
        entity_dir = self.output_dir / entity_type
        entity_dir.mkdir(exist_ok=True)
        total = len(items)
        batch_idx = 1
        for i in range(0, total, self.batch_size):
            batch = items[i:i+self.batch_size]
            filename = f"{entity_type}_{batch_idx:04d}.json"
            with open(entity_dir / filename, "w", encoding="utf-8") as f:
                json.dump(batch, f, indent=2, ensure_ascii=False)
            batch_idx += 1
        return total

    def write_sections(self, sections: List[Dict]) -> None:
        self._sections_written = self._write_batches("sections", sections)

    def write_topics(self, topics: List[Dict]) -> None:
        self._topics_written = self._write_batches("topics", topics)

    def write_variants(self, variants: List[Dict]) -> None:
        self._variants_written = self._write_batches("variants", variants)

    def write_groups(self, groups: List[Dict]) -> None:
        self._groups_written = self._write_batches("groups", groups)

    def write_fallbacks(self, fallbacks: List[Dict]) -> None:
        self._fallbacks_written = self._write_batches("fallbacks", fallbacks)

    def finalize(self, model_metadata: Dict[str, Any]) -> None:
        """Write the manifest.json file."""
        manifest = {
            "model_name": model_metadata["model_name"],
            "description": model_metadata.get("description", ""),
            "author": model_metadata.get("author", ""),
            "version": model_metadata.get("version", "1.0.0"),
            "alto_version": model_metadata.get("alto_version", "0.1a"),
            "created_at": model_metadata.get("created_at"),
            "updated_at": model_metadata.get("updated_at"),
            "section_count": self._sections_written,
            "topic_count": self._topics_written,
            "variant_count": self._variants_written,
            "group_count": self._groups_written,
            "fallback_count": self._fallbacks_written,
        }
        with open(self.output_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)