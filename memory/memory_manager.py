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
        else:
            memory = self.load_memory()
            self.save_memory(memory)

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
                "open_questions": [],
                "conversation_history": [],
                "action_history": [],
            },
            "metadata": {
                "version": "0.2",
                "prototype": "HADES por Voz",
                "last_updated": None,
            },
        }

    def _ensure_schema(self, memory: dict[str, Any]) -> dict[str, Any]:
        profile = memory.setdefault("user_profile", {})
        profile.setdefault("name", self.profile_name or "Usuario")
        profile.setdefault("profile_summary", "")
        profile.setdefault("patterns", [])
        profile.setdefault("open_questions", [])
        profile.setdefault("conversation_history", [])
        profile.setdefault("action_history", [])

        metadata = memory.setdefault("metadata", {})
        metadata.setdefault("version", "0.2")
        metadata.setdefault("prototype", "HADES por Voz")
        metadata.setdefault("last_updated", None)
        return memory

    def load_memory(self) -> dict[str, Any]:
        if not self.path:
            raise RuntimeError("No hay perfil activo. Primero definí un nombre de perfil.")

        with self.path.open("r", encoding="utf-8") as f:
            memory = json.load(f)

        return self._ensure_schema(memory)

    def save_memory(self, memory: dict[str, Any]) -> None:
        if not self.path:
            raise RuntimeError("No hay perfil activo. Primero definí un nombre de perfil.")

        memory = self._ensure_schema(memory)
        memory.setdefault("metadata", {})
        memory["metadata"]["last_updated"] = datetime.now().isoformat(timespec="seconds")

        with self.path.open("w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)


    STABILITY_CUES = [
        "normalmente", "suelo", "suele", "siempre", "casi siempre", "usualmente",
        "por lo general", "cada dia", "cada día", "todos los dias", "todos los días",
        "entre semana", "los lunes", "los martes", "los miercoles", "los miércoles",
        "los jueves", "los viernes", "los sabados", "los sábados", "los domingos",
        "prefiero", "me gusta", "no me gusta", "me interesa", "me sirve", "me cuesta",
        "tengo rutina", "mi rutina", "a menudo", "frecuentemente", "todos los días", "dias laborales",
        "días laborales", "lunes a viernes", "entre semana", "cada mañana", "todas las mañanas",
        "todos los dias laborales", "todos los días laborales",
    ]

    ONE_OFF_ACTION_CUES = [
        "alarma", "recordatorio", "recordame", "recuérdame", "acordame", "avísame", "avisame",
        "hoy", "mañana", "esta tarde", "esta noche", "ahorita", "luego", "más tarde", "mas tarde",
        "reunion", "reunión", "cliente", "cita", "cocinar", "empezar", "poner", "encender", "apagar",
    ]

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        text = (text or "").lower().strip()
        for src, dst in {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}.items():
            text = text.replace(src, dst)
        return text

    @classmethod
    def _pattern_is_stable_enough(cls, pattern: dict[str, Any]) -> bool:
        evidence = str(pattern.get("evidence", "")).strip()
        normal_behavior = str(pattern.get("normal_behavior", "")).strip()
        if not evidence or evidence.lower().startswith("hades"):
            return False

        combined = cls._normalize_text(f"{evidence} {normal_behavior} {pattern.get('trigger_or_condition', '')}")
        ptype = cls._normalize_text(str(pattern.get("type", "")))
        importance = cls._normalize_text(str(pattern.get("importance", "")))
        confidence = cls._normalize_text(str(pattern.get("confidence", "")))

        # Señales e incertidumbres suelen ser momentáneas; no las guardamos salvo que sean muy claras.
        if ptype in {"signal", "uncertainty"}:
            return any(cue in combined for cue in cls.STABILITY_CUES) and confidence == "high"

        has_stability_cue = any(cue in combined for cue in cls.STABILITY_CUES)
        has_one_off_cue = any(cue in combined for cue in cls.ONE_OFF_ACTION_CUES)

        # Si parece tarea/alarma/plan de una sola vez y no tiene lenguaje de rutina, no es patrón.
        if has_one_off_cue and not has_stability_cue:
            return False

        # No guardar cosas genéricas sin comportamiento normal.
        if not normal_behavior or cls._normalize_text(normal_behavior) in {"no especificado", "n/a", "ninguno"}:
            return False

        # Preferimos baja agresividad: sin señal de estabilidad, solo guardamos preferencias explícitas.
        if not has_stability_cue:
            return ptype == "preference" and any(cue in combined for cue in ["prefiero", "me gusta", "no me gusta", "me interesa"])

        # Evitar que el LLM marque todo como medio/alto sin base.
        if importance == "high" and confidence != "high":
            pattern["importance"] = "medium"

        return True

    @staticmethod
    def _pattern_key(pattern: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(pattern.get("type", "")).strip().lower(),
            str(pattern.get("domain", "")).strip().lower(),
            str(pattern.get("evidence", "")).strip().lower(),
        )

    def merge_extracted_patterns(self, extraction: dict[str, Any]) -> dict[str, Any]:
        memory = self.load_memory()
        profile = memory.setdefault("user_profile", {})

        if self.profile_name:
            profile["name"] = self.profile_name

        existing_patterns = profile.setdefault("patterns", [])
        existing_keys = {self._pattern_key(p) for p in existing_patterns if isinstance(p, dict)}
        accepted_new_patterns = 0

        for pattern in extraction.get("patterns", []) or []:
            if not isinstance(pattern, dict):
                continue
            if not self._pattern_is_stable_enough(pattern):
                continue
            key = self._pattern_key(pattern)
            if key in existing_keys:
                continue
            pattern.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
            existing_patterns.append(pattern)
            existing_keys.add(key)
            accepted_new_patterns += 1

        # Actualizar profile_summary solo cuando sí aceptamos patrones estables.
        # Esto evita que comandos puntuales como alarmas o hambre momentánea contaminen el resumen.
        new_summary = str(extraction.get("profile_summary", "")).strip()
        if new_summary and accepted_new_patterns > 0:
            old_summary = profile.get("profile_summary", "").strip()
            profile["profile_summary"] = (
                f"{old_summary}\n{new_summary}".strip()
                if old_summary and new_summary not in old_summary
                else new_summary
            )

        open_questions = profile.setdefault("open_questions", [])

        # Mantener pocas preguntas abiertas. La evaluación se hace conversando, no llenando memoria.
        for question in (extraction.get("open_questions", []) or [])[:1]:
            if isinstance(question, str) and question not in open_questions and len(open_questions) < 4:
                open_questions.append(question)

        self.save_memory(memory)
        return memory

    def append_conversation_turn(
        self,
        user_text: str,
        assistant_text: str,
        source: str = "voice",
    ) -> dict[str, Any]:
        memory = self.load_memory()
        profile = memory.setdefault("user_profile", {})
        history = profile.setdefault("conversation_history", [])
        history.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "source": source,
                "user": user_text,
                "hades": assistant_text,
            }
        )
        self.save_memory(memory)
        return memory

    def append_action(self, action: dict[str, Any]) -> dict[str, Any]:
        memory = self.load_memory()
        profile = memory.setdefault("user_profile", {})
        actions = profile.setdefault("action_history", [])
        action = dict(action)
        action.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        action.setdefault("status", "proposed")
        actions.append(action)
        self.save_memory(memory)
        return memory

    def update_last_proposed_action(self, status: str, note: str | None = None) -> dict[str, Any] | None:
        memory = self.load_memory()
        actions = memory.setdefault("user_profile", {}).setdefault("action_history", [])
        for action in reversed(actions):
            if action.get("status") == "proposed":
                action["status"] = status
                action["resolved_at"] = datetime.now().isoformat(timespec="seconds")
                if note:
                    action["resolution_note"] = note
                self.save_memory(memory)
                return action
        return None

    def has_pending_action(self) -> bool:
        memory = self.load_memory()
        actions = memory.setdefault("user_profile", {}).setdefault("action_history", [])
        return any(action.get("status") == "proposed" for action in actions)

    def recent_conversation_history(self, limit: int = 8) -> list[dict[str, Any]]:
        memory = self.load_memory()
        history = memory.setdefault("user_profile", {}).setdefault("conversation_history", [])
        return history[-limit:]

    def pretty_memory(self) -> str:
        memory = self.load_memory()
        return json.dumps(memory, indent=2, ensure_ascii=False)

    def list_profiles(self) -> list[str]:
        profiles = []

        for file in self.memory_dir.glob("_*.json"):
            name = file.stem.removeprefix("_")
            profiles.append(name)

        return sorted(profiles)
