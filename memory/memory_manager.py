import json
import re
from datetime import datetime, timedelta
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

    def _ensure_active_profile(self) -> None:
        # Default defensivo para pruebas o usos internos donde se llama load_memory()
        # antes de seleccionar perfil. El menú principal sigue seleccionando perfil explícitamente.
        if not self.path or not self.profile_name:
            self.set_profile("General")

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
        profile.setdefault("name", self.profile_name or "General")
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
        self._ensure_active_profile()
        assert self.path is not None

        if not self.path.exists():
            self.save_memory(self.empty_memory(self.profile_name or "General"))

        with self.path.open("r", encoding="utf-8") as f:
            memory = json.load(f)

        return self._ensure_schema(memory)

    def save_memory(self, memory: dict[str, Any]) -> None:
        self._ensure_active_profile() if self.path is None else None
        assert self.path is not None

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
        "tengo rutina", "mi rutina", "a menudo", "frecuentemente", "dias laborales",
        "días laborales", "lunes a viernes", "cada mañana", "todas las mañanas",
        "todos los dias laborales", "todos los días laborales",
        "repetido", "repetida", "repetidamente", "varias veces", "dos veces",
    ]

    ONE_OFF_ACTION_CUES = [
        "alarma", "recordatorio", "recordame", "recuérdame", "acordame", "avísame", "avisame",
        "hoy", "mañana", "esta tarde", "esta noche", "ahorita", "ahora", "luego", "más tarde", "mas tarde",
        "reunion", "reunión", "cliente", "cita", "cocinar", "preparar", "empezar", "poner",
        "encender", "apagar", "salir", "ir a comer",
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

        if ptype in {"signal", "uncertainty"}:
            return any(cue in combined for cue in cls.STABILITY_CUES) and confidence == "high"

        has_stability_cue = any(cue in combined for cue in cls.STABILITY_CUES)
        has_one_off_cue = any(cue in combined for cue in cls.ONE_OFF_ACTION_CUES)

        if has_one_off_cue and not has_stability_cue:
            return False

        if not normal_behavior or cls._normalize_text(normal_behavior) in {"no especificado", "n/a", "ninguno"}:
            return False

        if not has_stability_cue:
            return ptype == "preference" and any(
                cue in combined for cue in ["prefiero", "me gusta", "no me gusta", "me interesa"]
            )

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

        new_summary = str(extraction.get("profile_summary", "")).strip()
        if new_summary and accepted_new_patterns > 0:
            old_summary = profile.get("profile_summary", "").strip()
            profile["profile_summary"] = (
                f"{old_summary}\n{new_summary}".strip()
                if old_summary and new_summary not in old_summary
                else new_summary
            )

        open_questions = profile.setdefault("open_questions", [])
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

    @staticmethod
    def _parse_action_time(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @classmethod
    def _is_recent_action(cls, action: dict[str, Any], max_age_minutes: int) -> bool:
        created_at = cls._parse_action_time(action.get("created_at"))
        if not created_at:
            return False
        return datetime.now() - created_at <= timedelta(minutes=max_age_minutes)

    def get_recent_pending_action(self, max_age_minutes: int = 10) -> dict[str, Any] | None:
        memory = self.load_memory()
        actions = memory.setdefault("user_profile", {}).setdefault("action_history", [])
        for action in reversed(actions):
            if not isinstance(action, dict):
                continue
            if action.get("status") == "proposed" and self._is_recent_action(action, max_age_minutes):
                return action
        return None

    def update_last_proposed_action(
        self,
        status: str,
        note: str | None = None,
        max_age_minutes: int = 10,
    ) -> dict[str, Any] | None:
        memory = self.load_memory()
        actions = memory.setdefault("user_profile", {}).setdefault("action_history", [])
        for action in reversed(actions):
            if not isinstance(action, dict):
                continue
            if action.get("status") == "proposed" and self._is_recent_action(action, max_age_minutes):
                action["status"] = status
                action["resolved_at"] = datetime.now().isoformat(timespec="seconds")
                if note:
                    action["resolution_note"] = note
                self.save_memory(memory)
                return action
        return None

    def has_pending_action(self, max_age_minutes: int = 10) -> bool:
        return self.get_recent_pending_action(max_age_minutes=max_age_minutes) is not None



    def remove_last_action(self) -> dict[str, Any] | None:
        """Elimina la última acción guardada en action_history y devuelve una copia."""
        memory = self.load_memory()
        actions = memory.setdefault("user_profile", {}).setdefault("action_history", [])
        for idx in range(len(actions) - 1, -1, -1):
            action = actions[idx]
            if isinstance(action, dict):
                removed = actions.pop(idx)
                self.save_memory(memory)
                return removed
        return None

    def remove_last_pattern(self) -> dict[str, Any] | None:
        """Elimina el último patrón guardado y devuelve una copia."""
        memory = self.load_memory()
        patterns = memory.setdefault("user_profile", {}).setdefault("patterns", [])
        for idx in range(len(patterns) - 1, -1, -1):
            pattern = patterns[idx]
            if isinstance(pattern, dict):
                removed = patterns.pop(idx)
                self.save_memory(memory)
                return removed
        return None

    def remove_last_memory_item(self) -> tuple[str, dict[str, Any]] | None:
        """Elimina el último elemento de memoria útil: acción o patrón.

        Se usa para comandos como "olvida eso". No borra conversation_history,
        porque la conversación funciona como registro de auditoría de la sesión.
        """
        memory = self.load_memory()
        profile = memory.setdefault("user_profile", {})
        actions = profile.setdefault("action_history", [])
        patterns = profile.setdefault("patterns", [])

        last_action_idx = next((i for i in range(len(actions) - 1, -1, -1) if isinstance(actions[i], dict)), None)
        last_pattern_idx = next((i for i in range(len(patterns) - 1, -1, -1) if isinstance(patterns[i], dict)), None)

        if last_action_idx is None and last_pattern_idx is None:
            return None
        if last_pattern_idx is None:
            removed = actions.pop(last_action_idx)
            self.save_memory(memory)
            return "action", removed
        if last_action_idx is None:
            removed = patterns.pop(last_pattern_idx)
            self.save_memory(memory)
            return "pattern", removed

        action_time = self._parse_action_time(actions[last_action_idx].get("created_at")) or datetime.min
        pattern_time = self._parse_action_time(patterns[last_pattern_idx].get("created_at")) or datetime.min
        # Si empatan en el mismo segundo, preferimos patrón: normalmente se extrae
        # después de la acción dentro del mismo turno y "olvida eso" suele apuntar
        # a lo último que el sistema aprendió.
        if pattern_time >= action_time:
            removed = patterns.pop(last_pattern_idx)
            self.save_memory(memory)
            return "pattern", removed
        removed = actions.pop(last_action_idx)
        self.save_memory(memory)
        return "action", removed

    def list_actions(
        self,
        action_types: set[str] | None = None,
        limit: int | None = 10,
        include_rejected: bool = False,
    ) -> list[dict[str, Any]]:
        """Devuelve acciones guardadas con índice real dentro de action_history.

        El índice se mantiene para poder referenciar/actualizar/cancelar una acción
        concreta si el usuario escoge una opción de la lista.
        """
        memory = self.load_memory()
        actions = memory.setdefault("user_profile", {}).setdefault("action_history", [])
        out: list[dict[str, Any]] = []
        for idx, action in enumerate(actions):
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("type", "")).strip().lower()
            status = str(action.get("status", "")).strip().lower()
            if action_types is not None and action_type not in action_types:
                continue
            if not include_rejected and status == "rejected":
                continue
            item = dict(action)
            item["_memory_index"] = idx
            out.append(item)
        if limit is not None:
            out = out[-limit:]
        return out

    def update_action_at_index(self, index: int, updates: dict[str, Any]) -> dict[str, Any] | None:
        memory = self.load_memory()
        actions = memory.setdefault("user_profile", {}).setdefault("action_history", [])
        if not (0 <= index < len(actions)) or not isinstance(actions[index], dict):
            return None
        actions[index].update(updates)
        actions[index]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.save_memory(memory)
        return dict(actions[index])

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
