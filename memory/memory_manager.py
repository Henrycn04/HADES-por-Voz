import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import Settings


class MemoryManager:
    def __init__(self, settings: Settings):
        self.memory_dir: Path = settings.memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.profile_name: str | None = None
        self.path: Path | None = None

    @staticmethod
    def sanitize_profile_name(name: str) -> str:
        """
        Convierte nombres como:
        'José Pablo' -> 'Jose_Pablo' no garantiza quitar tildes,
        pero sí evita caracteres raros para el archivo.
        """
        clean = name.strip()
        clean = clean.replace(" ", "_")
        clean = re.sub(r"[^a-zA-Z0-9_áéíóúÁÉÍÓÚñÑ-]", "", clean)
        return clean or "Usuario"

    def set_profile(self, profile_name: str) -> None:
        clean_name = self.sanitize_profile_name(profile_name)
        self.profile_name = clean_name
        self.path = self.memory_dir / f"_{clean_name}.json"

        if not self.path.exists():
            self.save_memory(self.empty_memory(clean_name))

    def has_active_profile(self) -> bool:
        return self.profile_name is not None and self.path is not None

    def get_active_profile_name(self) -> str:
        return self.profile_name or "Sin perfil"

    @staticmethod
    def empty_memory(profile_name: str) -> dict[str, Any]:
        return {
            "user_profile": {
                "name": profile_name,
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
        if not self.path:
            raise RuntimeError("No hay perfil activo. Primero definí un nombre de perfil.")

        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_memory(self, memory: dict[str, Any]) -> None:
        if not self.path:
            raise RuntimeError("No hay perfil activo. Primero definí un nombre de perfil.")

        memory.setdefault("metadata", {})
        memory["metadata"]["last_updated"] = datetime.now().isoformat(timespec="seconds")

        with self.path.open("w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)

    def merge_extracted_patterns(self, extraction: dict[str, Any]) -> dict[str, Any]:
        memory = self.load_memory()
        profile = memory.setdefault("user_profile", {})

        if self.profile_name:
            profile["name"] = self.profile_name

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

    def list_profiles(self) -> list[str]:
        profiles = []

        for file in self.memory_dir.glob("_*.json"):
            name = file.stem.removeprefix("_")
            profiles.append(name)

        return sorted(profiles)