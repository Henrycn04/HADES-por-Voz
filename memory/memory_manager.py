import json
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import Settings


class MemoryManager:
    def __init__(self, settings: Settings):
        self.path: Path = settings.memory_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save_memory(self.empty_memory())

    @staticmethod
    def empty_memory() -> dict[str, Any]:
        return {
            "user_profile": {
                "profile_summary": "",
                "patterns": [],
                "open_questions": []
            },
            "metadata": {
                "version": "0.1",
                "prototype": "HADES por Voz",
                "last_updated": None
            }
        }

    def load_memory(self) -> dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_memory(self, memory: dict[str, Any]) -> None:
        memory.setdefault("metadata", {})
        memory["metadata"]["last_updated"] = datetime.now().isoformat(timespec="seconds")
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)

    def merge_extracted_patterns(self, extraction: dict[str, Any]) -> dict[str, Any]:
        memory = self.load_memory()
        profile = memory.setdefault("user_profile", {})

        new_summary = extraction.get("profile_summary", "").strip()
        if new_summary:
            old_summary = profile.get("profile_summary", "").strip()
            profile["profile_summary"] = (
                f"{old_summary}\n{new_summary}".strip()
                if old_summary and new_summary not in old_summary
                else new_summary
            )

        existing_patterns = profile.setdefault("patterns", [])
        for pattern in extraction.get("patterns", []):
            pattern["created_at"] = datetime.now().isoformat(timespec="seconds")
            existing_patterns.append(pattern)

        open_questions = profile.setdefault("open_questions", [])
        for question in extraction.get("open_questions", []):
            if question not in open_questions:
                open_questions.append(question)

        self.save_memory(memory)
        return memory

    def pretty_memory(self) -> str:
        memory = self.load_memory()
        return json.dumps(memory, indent=2, ensure_ascii=False)
