import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config.settings import Settings
from memory.memory_manager import MemoryManager
from pattern_extraction.pattern_extractor import PatternExtractor
from voice.kokoro_tts import KokoroTTS
from voice.speech_to_text import WhisperSTT
from voice.wake_word import WakeWordListener
from voice.audio_cues import AudioCuePlayer


ASSISTANT_RESPONSE_SCHEMA = """
Respondé SOLO con JSON válido usando esta forma:
{
  "response": "respuesta breve, natural y útil que HADES diría en voz alta",
  "proposed_actions": [
    {
      "type": "suggestion | reminder | alarm | planning | question | routine_adjustment | music | light | do_not_disturb | note | other",
      "domain": "sleep | study | work | food | relaxation | home | energy | emotional_state | other",
      "status": "proposed | accepted | rejected | simulated",
      "description": "acción concreta manejada o propuesta por HADES",
      "trigger_or_condition": "qué dijo el usuario o qué patrón activó la acción",
      "meaning": "por qué esta acción puede ser útil",
      "importance": "low | medium | high",
      "confidence": "low | medium | high",
      "evidence": "frase concreta del usuario o patrón de memoria usado"
    }
  ],
  "needs_pattern_extraction": true,
  "listen_for_followup": false
}
"""


class HadesAssistant:
    """
    Modo vivo de HADES:
    wake word -> STT -> LLM -> TTS -> memoria.
    La unidad principal es el perfil, no una sesión experimental.
    """

    def __init__(
        self,
        settings: Settings,
        llm: Any,
        memory_manager: MemoryManager,
        extractor: PatternExtractor,
    ):
        self.settings = settings
        self.llm = llm
        self.memory_manager = memory_manager
        self.extractor = extractor
        self.tts = KokoroTTS(settings)
        self.stt = WhisperSTT(settings)
        self.wake_listener = WakeWordListener(settings)
        self.audio_cues = AudioCuePlayer(settings)

    def run_until_menu(self) -> None:
        if not self.memory_manager.has_active_profile():
            raise RuntimeError("No hay perfil activo para Modo HADES.")

        profile = self.memory_manager.get_active_profile_name()
        print("\n" + "=" * 64)
        print(f"Modo HADES activo | Perfil: {profile}")
        print(f"Wake word actual: {self.settings.wake_word}")
        print("Para volver al menú: activá HADES y decí 'volver al menú'.")
        print("Después de una pregunta de HADES, podés responder sin repetir la wake word.")
        print("=" * 64)

        active_mode = False

        while True:
            if not active_mode:
                print("\n[HADES] Modo pasivo: escuchando wake word...")
                self.audio_cues.passive_listening()
                score = self.wake_listener.wait_for_wake_word()
                print(f"[HADES] Wake word detectada | score={score:.2f}")
                self.audio_cues.wake_detected()
                print("[HADES] Activado. Hablá ahora con naturalidad.")
            else:
                print("\n[HADES] Modo activo: escuchando respuesta sin wake word...")
                self.audio_cues.followup_listening()

            user_text, audio_path = self.stt.listen_command()
            user_text = self._clean_transcript(user_text)

            if not user_text:
                if active_mode:
                    print("[HADES] No hubo respuesta. Vuelvo a modo pasivo.")
                    active_mode = False
                else:
                    print("[HADES] No escuché un comando claro. Volviendo a escuchar wake word.")
                continue

            print(f"\nUsuario: {user_text}")

            if self._is_exit_command(user_text):
                farewell = "Perfecto, vuelvo al menú principal. Dejé guardada la memoria de este perfil."
                print(f"HADES: {farewell}")
                self.tts.speak(farewell)
                self.memory_manager.append_conversation_turn(
                    user_text=user_text,
                    assistant_text=farewell,
                    source="voice",
                )
                return

            action_resolution = self._resolve_pending_action_if_needed(user_text)
            response_payload = self._generate_response(user_text, action_resolution=action_resolution)

            response = str(response_payload.get("response", "")).strip()
            if not response:
                response = "Entiendo. Podés contarme un poco más para ayudarte mejor."

            print(f"HADES: {response}")
            self.tts.speak(response)

            self.memory_manager.append_conversation_turn(
                user_text=user_text,
                assistant_text=response,
                source="voice",
            )

            for action in response_payload.get("proposed_actions", []) or []:
                if isinstance(action, dict):
                    self.memory_manager.append_action(action)

            if bool(response_payload.get("needs_pattern_extraction", False)):
                self._extract_patterns_from_turn(user_text)

            active_mode = self._should_listen_for_followup(response, response_payload)
            if active_mode:
                print("[HADES] Quedo activo para escuchar tu respuesta sin wake word.")
            else:
                print("[HADES] Vuelvo a modo pasivo.")

    def _generate_response(self, user_text: str, action_resolution: str | None = None) -> dict[str, Any]:
        memory = self.memory_manager.load_memory()
        profile = memory.get("user_profile", {})
        now_info = self._current_time_context()
        current_command_hint = self._current_command_hint(user_text)

        memory_context = {
            "name": profile.get("name"),
            "profile_summary": profile.get("profile_summary", ""),
            "patterns": profile.get("patterns", []),
            "open_questions": profile.get("open_questions", []),
            "recent_conversation_history": profile.get("conversation_history", [])[-8:],
            "recent_action_history": profile.get("action_history", [])[-6:],
        }

        prompt = f"""
Eres HADES, un asistente doméstico conversacional con memoria contextual.

Diferencia central frente a Google Home o Alexa:
HADES no solo responde comandos. Aprende progresivamente a la persona, sus rutinas,
preferencias, prioridades, excepciones y señales de cambio. Mientras más se usa, mejor
comprende y predice el contexto del usuario.

Contexto temporal obligatorio:
{now_info}

Perfil y memoria actual:
{json.dumps(memory_context, indent=2, ensure_ascii=False)}

Usuario acaba de decir:
{user_text}

Pista determinística sobre el comando actual:
{current_command_hint}

Resolución de acción pendiente, si aplica:
{action_resolution or "ninguna"}

Reglas de comportamiento:
- Respondé como asistente doméstico, no como ChatGPT. Sé breve, útil y directo.
- PRIORIDAD: el comando actual del usuario manda sobre la memoria previa. La memoria solo sirve como contexto, no para reemplazar lo que acaba de pedir.
- No reutilicés una alarma, hora, rutina o configuración anterior salvo que el usuario diga claramente "la misma", "como siempre", "igual que antes" o esté respondiendo a una acción pendiente.
- Si el usuario pide una alarma/recordatorio puntual y menciona un momento del día, interpretá la hora con ese momento: "noche" => PM, "tarde" => PM, "mañana" => AM. Ejemplo: "ahora en la noche... a las siete" = 7:00 PM / 19:00, NO 7:00 AM.
- Si el usuario dice "ahora", "hoy", "esta noche", "en la noche" o "más tarde", tratá la acción como puntual, no recurrente, salvo que diga "todos los días", "siempre", "lunes a viernes" o similar.
- HADES puede simular acciones tipo asistente: alarmas, recordatorios, música, luces, no molestar, notas y rutinas simples.
- HADES NO puede buscar en internet, abrir páginas, consultar noticias, recetas externas, precios ni información en línea. Si el usuario pide eso, decí brevemente que este prototipo no tiene internet y ofrecé una alternativa local como crear recordatorio, nota o plan simple.
- Si el usuario da un comando puntual y claro, confirmá la acción simulada y TERMINÁ. No hagás preguntas extra.
- Si el usuario dice "no", "déjalo así", "dejalo", "cancelar" o algo parecido, respetá eso, confirmá corto y no insistás.
- No hagás más de una pregunta. Preguntá solo si es necesario para ejecutar el comando o si el usuario pidió ayuda abierta.
- Preferí sugerencias de sí/no cuando la proactividad sea útil. Ejemplo: "Puedo ayudarte a reorganizarlo. ¿Querés que lo haga?"
- No conviertas cada respuesta en follow-up. listen_for_followup debe ser true solo cuando realmente esperás una confirmación o dato necesario.
- Si proponés una acción que necesita permiso, poné status "proposed" y listen_for_followup true.
- Si el usuario pidió directamente una alarma, recordatorio, luz, música, no molestar o nota, registrá la acción con status "simulated" y listen_for_followup false.
- Si el usuario aceptó una acción pendiente, concretá la ayuda y registrá con status "simulated" o "accepted". No preguntés otra cosa al final.
- Si la frase contiene datos estables sobre rutina/preferencia/excepción, needs_pattern_extraction debe ser true.
- Si es solo una orden puntual, estado momentáneo o plan de hoy, needs_pattern_extraction debe ser false.
- Nunca uses como patrón una sugerencia que HADES dijo. La memoria de patrones solo se aprende del usuario.

Formato requerido:
{ASSISTANT_RESPONSE_SCHEMA}
"""
        try:
            data = self.llm.generate_json(
                prompt,
                temperature=self.settings.ollama_conversation_temperature,
            )
            data.setdefault("proposed_actions", [])
            data.setdefault("needs_pattern_extraction", False)
            data.setdefault("listen_for_followup", False)
            data["proposed_actions"] = self._sanitize_actions(data.get("proposed_actions", []))
            data = self._apply_temporal_safety_corrections(data, user_text)
            return data
        except Exception as exc:
            print(f"[HADES] No pude parsear respuesta JSON del LLM: {exc}")
            text = self.llm.generate_text(prompt, temperature=0.4)
            return {
                "response": text or "Entiendo. Contame un poco más para ayudarte mejor.",
                "proposed_actions": [],
                "needs_pattern_extraction": False,
                "listen_for_followup": False,
            }

    def _extract_patterns_from_turn(self, user_text: str) -> None:
        # Importante: patrones solo desde lo que dijo el usuario, no desde la respuesta de HADES.
        transcript = f"Usuario: {user_text}"
        try:
            extraction = self.extractor.extract(transcript)
            self.memory_manager.merge_extracted_patterns(extraction)
        except Exception as exc:
            print(f"[PatternExtractor] No se pudo actualizar memoria desde este turno: {exc}")

    def _resolve_pending_action_if_needed(self, user_text: str) -> str | None:
        if not self.memory_manager.has_pending_action():
            return None

        normalized = self._normalize(user_text)

        accepted = any(
            phrase in normalized
            for phrase in [
                "si",
                "sí",
                "dale",
                "ok",
                "hagamoslo",
                "hagámoslo",
                "de acuerdo",
                "acepto",
                "claro",
            ]
        )
        rejected = any(
            phrase in normalized
            for phrase in [
                "no",
                "mejor no",
                "cancelar",
                "rechazo",
                "dejalo",
                "déjalo",
            ]
        )

        # Evita marcar como rechazo una frase larga donde aparece "no" de forma normal.
        if rejected and len(normalized.split()) > 5 and not any(p in normalized for p in ["mejor no", "cancelar", "rechazo"]):
            rejected = False

        if accepted:
            self.memory_manager.update_last_proposed_action("accepted", note=user_text)
            return "El usuario aceptó la última acción propuesta. Ahora HADES debe concretar la ayuda de forma útil."

        if rejected:
            self.memory_manager.update_last_proposed_action("rejected", note=user_text)
            return "El usuario rechazó la última acción propuesta. HADES debe respetar la decisión y no insistir."

        return None


    @staticmethod
    def _sanitize_actions(actions: Any) -> list[dict[str, Any]]:
        """Filtra acciones demasiado vagas o que no son acciones reales del asistente."""
        if not isinstance(actions, list):
            return []
        clean: list[dict[str, Any]] = []
        allowed_status = {"proposed", "accepted", "rejected", "simulated"}
        for action in actions:
            if not isinstance(action, dict):
                continue
            action = dict(action)
            description = str(action.get("description", "")).strip()
            evidence = str(action.get("evidence", "")).strip()
            if not description or not evidence:
                continue
            action_type = str(action.get("type", "other")).strip().lower()
            # Las preguntas ya quedan en conversation_history.
            # action_history debe representar acciones concretas, no entrevista.
            if action_type == "question":
                continue
            status = str(action.get("status", "proposed")).strip().lower()
            if status not in allowed_status:
                status = "proposed"
            action["status"] = status
            action["importance"] = str(action.get("importance", "low")).strip().lower() or "low"
            action["confidence"] = str(action.get("confidence", "medium")).strip().lower() or "medium"
            clean.append(action)
        return clean[:3]
    @staticmethod
    def _apply_temporal_safety_corrections(payload: dict[str, Any], user_text: str) -> dict[str, Any]:
        """Corrige errores peligrosos de AM/PM causados por memoria previa."""
        normalized = HadesAssistant._normalize(user_text)

        mentions_night = any(term in normalized for term in ["noche", "esta noche", "en la noche"])
        mentions_afternoon = any(term in normalized for term in ["tarde", "esta tarde"])
        mentions_seven = bool(re.search(r"\b(7|siete)\b", normalized))
        mentions_six = bool(re.search(r"\b(6|seis)\b", normalized))

        replacement: tuple[str, str] | None = None

        if mentions_night and mentions_seven:
            replacement = ("7:00 AM", "7:00 PM")
        elif mentions_afternoon and mentions_seven:
            replacement = ("7:00 AM", "7:00 PM")
        elif mentions_afternoon and mentions_six:
            replacement = ("6:00 AM", "6:00 PM")

        if not replacement:
            return payload

        bad, good = replacement
        variants = [
            bad,
            bad.replace(":00", ""),
            bad.lower(),
            bad.replace("AM", "a.m."),
            bad.replace("AM", "a. m."),
        ]

        def fix_text(value: Any) -> Any:
            if not isinstance(value, str):
                return value

            fixed = value

            for variant in variants:
                fixed = fixed.replace(variant, good)

            if good == "7:00 PM":
                fixed = re.sub(
                    r"\b7\s*(a\.?\s*m\.?|AM)\b",
                    "7:00 PM",
                    fixed,
                    flags=re.IGNORECASE,
                )
            elif good == "6:00 PM":
                fixed = re.sub(
                    r"\b6\s*(a\.?\s*m\.?|AM)\b",
                    "6:00 PM",
                    fixed,
                    flags=re.IGNORECASE,
                )

            return fixed

        payload["response"] = fix_text(payload.get("response", ""))

        for action in payload.get("proposed_actions", []) or []:
            if isinstance(action, dict):
                for key in ["description", "trigger_or_condition", "meaning", "evidence"]:
                    action[key] = fix_text(action.get(key, ""))

        return payload


    @staticmethod
    def _current_command_hint(text: str) -> str:
        """
        Pistas simples para evitar que el LLM arrastre una rutina vieja sobre un comando actual.
        No ejecuta acciones; solo aclara intención temporal para el prompt.
        """
        normalized = HadesAssistant._normalize(text or "")
        hints: list[str] = []

        mentions_alarm = any(
            word in normalized
            for word in [
                "alarma",
                "arma",
                "recordatorio",
                "recordame",
                "avisame",
                "avisa",
                "acordame",
            ]
        )

        mentions_night = any(
            word in normalized
            for word in ["noche", "esta noche", "en la noche"]
        )

        mentions_afternoon = any(
            word in normalized
            for word in ["tarde", "esta tarde"]
        )

        mentions_morning = any(
            word in normalized
            for word in ["manana", "mañana", "la manana", "la mañana"]
        )

        mentions_one_off = any(
            word in normalized
            for word in ["ahora", "hoy", "esta noche", "esta tarde", "mas tarde", "más tarde"]
        )

        mentions_recurring = any(
            word in normalized
            for word in [
                "todos los dias",
                "todos los días",
                "siempre",
                "lunes a viernes",
                "dias laborales",
                "días laborales",
                "cada dia",
                "cada día",
            ]
        )

        if mentions_alarm:
            hints.append("El usuario probablemente está pidiendo una alarma o recordatorio.")

        if mentions_night:
            hints.append("Si el usuario menciona 'noche' y una hora como 'siete', interpretá esa hora como PM: 7:00 PM / 19:00.")
        elif mentions_afternoon:
            hints.append("Si el usuario menciona 'tarde' y una hora como seis/siete, interpretá esa hora como PM.")
        elif mentions_morning:
            hints.append("Si el usuario menciona 'mañana' como parte del día y una hora, interpretá esa hora como AM.")

        if mentions_one_off and not mentions_recurring:
            hints.append("La frase suena a acción puntual de hoy/esta noche; no la conviertas en rutina recurrente.")

        if mentions_recurring:
            hints.append("La frase indica recurrencia; puede ser rutina si también hay horario o hábito claro.")

        return "\n".join(f"- {hint}" for hint in hints) if hints else "Sin pista especial; seguí el comando actual literal."
    def _should_listen_for_followup(self, response: str, payload: dict[str, Any]) -> bool:
        """
        El LLM decide explícitamente si necesita follow-up.
        Evitamos quedarnos activos solo porque la respuesta tenga una pregunta retórica.
        """
        if bool(payload.get("listen_for_followup", False)):
            return True
        actions = payload.get("proposed_actions", []) or []
        return any(isinstance(action, dict) and action.get("status") == "proposed" for action in actions)

    @staticmethod
    def _is_exit_command(text: str) -> bool:
        normalized = HadesAssistant._normalize(text)
        exit_phrases = [
            "volver al menu",
            "volver al menú",
            "regresar al menu",
            "regresar al menú",
            "salir del modo hades",
            "cerrar modo hades",
            "terminar modo hades",
            "finalizar modo hades",
            "cerrar sesion",
            "cerrar sesión",
        ]
        return any(phrase in normalized for phrase in exit_phrases)

    @staticmethod
    def _clean_transcript(text: str) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        if len(re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]", text)) < 3:
            return ""
        return text

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower().strip()
        replacements = {
            "á": "a",
            "é": "e",
            "í": "i",
            "ó": "o",
            "ú": "u",
            "ñ": "n",
        }
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        return text

    @staticmethod
    def _current_time_context() -> str:
        try:
            now = datetime.now(ZoneInfo("America/Costa_Rica"))
        except Exception:
            now = datetime.now()

        days = {
            0: "lunes",
            1: "martes",
            2: "miércoles",
            3: "jueves",
            4: "viernes",
            5: "sábado",
            6: "domingo",
        }
        return (
            f"Fecha actual: {now.date().isoformat()}\n"
            f"Día de la semana: {days.get(now.weekday(), now.strftime('%A'))}\n"
            f"Hora local: {now.strftime('%H:%M')}\n"
            "Zona horaria: America/Costa_Rica"
        )
