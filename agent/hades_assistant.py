import json
import re
import threading
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
from ui.terminal_input import IdleInput, TerminalInputController


ASSISTANT_RESPONSE_SCHEMA = """
Respondé SOLO con JSON válido usando esta forma:
{
  "response": "respuesta breve, natural y útil que HADES diría en voz alta",
  "proposed_actions": [
    {
      "type": "suggestion | reminder | alarm | alarm_update | alarm_cancel | reminder_update | reminder_cancel | planning | question | routine_adjustment | music | light | do_not_disturb | note | other",
      "domain": "sleep | study | work | food | health | relaxation | home | energy | emotional_state | other",
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
        self.wake_listener = WakeWordListener(settings) if settings.enable_wake_word else None
        self.audio_cues = AudioCuePlayer(settings)
        self.terminal = TerminalInputController(enable_wake_word=settings.enable_wake_word)
        self.pending_action_choice: dict[str, Any] | None = None

    def run_until_menu(self) -> None:
        if not self.memory_manager.has_active_profile():
            raise RuntimeError("No hay perfil activo para Modo HADES.")

        profile = self.memory_manager.get_active_profile_name()
        print("\n" + "=" * 64)
        print(f"Modo HADES activo | Perfil: {profile}")
        if self.settings.enable_wake_word:
            print(f"Wake word actual: {self.settings.wake_word}")
        else:
            print("Wake word desactivada por configuración; usá chat o ESPACIO.")
        print("Controles:")
        print("- Escribí en Chat> y presioná Enter para enviar texto.")
        print("- Presioná ESPACIO con Chat> vacío para grabar por voz.")
        print("- También podés activar por wake word.")
        print("- Presioná ESC para cancelar grabación, transcripción, LLM o TTS y volver a idle.")
        print("- Para volver al menú: escribí o decí 'volver al menú'.")
        print("=" * 64)

        active_mode = False

        while True:
            try:
                if active_mode:
                    print("\n[HADES] Modo activo: escuchando respuesta sin wake word. ESC cancela.")
                    self.audio_cues.followup_listening()
                    user_text = self._listen_voice_command(source="voice_followup")
                    source = "voice"
                    if not user_text:
                        print("[HADES] No hubo respuesta. Vuelvo a idle.")
                        active_mode = False
                        continue
                else:
                    idle_input = self.terminal.wait_for_idle_input(self.wake_listener)
                    user_text, source = self._resolve_idle_input(idle_input)
                    if not user_text:
                        active_mode = False
                        continue

                next_active = self._process_user_text(user_text=user_text, source=source)
                if next_active is None:
                    return
                active_mode = next_active
            except KeyboardInterrupt:
                print("\n[HADES] Interacción interrumpida. Vuelvo al menú.")
                return

    def _resolve_idle_input(self, idle_input: IdleInput) -> tuple[str, str]:
        if idle_input.kind == "chat":
            return idle_input.text.strip(), "chat"

        if idle_input.kind == "space_voice":
            print("[HADES] Activado por teclado. Hablá ahora con naturalidad.")
            self.audio_cues.wake_detected()
            return self._listen_voice_command(source="voice_space"), "voice"

        if idle_input.kind == "wake_word":
            score_text = f" | score={idle_input.wake_score:.2f}" if idle_input.wake_score is not None else ""
            print(f"[HADES] Wake word detectada{score_text}")
            self.audio_cues.wake_detected()
            print("[HADES] Activado. Hablá ahora con naturalidad.")
            return self._listen_voice_command(source="voice_wake"), "voice"

        return "", "chat"

    def _listen_voice_command(self, source: str = "voice") -> str:
        cancel_event = threading.Event()
        result, canceled = self.terminal.run_cancelable(
            "STT/grabación",
            lambda: self.stt.listen_command(cancel_event=cancel_event),
            cancel_event=cancel_event,
        )
        if canceled or not result:
            return ""
        user_text, _audio_path = result
        return self._clean_transcript(user_text)

    def _process_user_text(self, user_text: str, source: str = "voice") -> bool | None:
        user_text = self._clean_transcript(user_text) if source != "chat" else user_text.strip()
        if not user_text:
            return False

        print(f"\nUsuario ({source}): {user_text}")

        if self._is_exit_command(user_text):
            farewell = "Perfecto, vuelvo al menú principal. Dejé guardada la memoria de este perfil."
            print(f"HADES: {farewell}")
            self._speak_cancelable(farewell)
            self.memory_manager.append_conversation_turn(
                user_text=user_text,
                assistant_text=farewell,
                source=source,
            )
            return None

        special_result = self._handle_deterministic_memory_or_action_command(user_text, source)
        if special_result is not None:
            return special_result

        action_resolution = self._resolve_pending_action_if_needed(user_text)

        cancel_event = threading.Event()
        response_payload, canceled = self.terminal.run_cancelable(
            "respuesta LLM",
            lambda: self._generate_response(user_text, action_resolution=action_resolution),
            cancel_event=cancel_event,
        )
        if canceled or not response_payload:
            return False

        response = str(response_payload.get("response", "")).strip()
        if not response:
            response = "Entiendo. Podés contarme un poco más para ayudarte mejor."

        print(f"HADES: {response}")

        if not self._speak_cancelable(response):
            return False

        self.memory_manager.append_conversation_turn(
            user_text=user_text,
            assistant_text=response,
            source=source,
        )

        # Además de la extracción por LLM, revisamos repeticiones simples del usuario.
        # Esto permite que frases repetidas como "voy a dormir a las 10" se consoliden
        # como patrón sin obligar al usuario a decir "normalmente".
        self._infer_repeated_patterns_from_history()

        for action in response_payload.get("proposed_actions", []) or []:
            if isinstance(action, dict):
                self.memory_manager.append_action(action)

        if bool(response_payload.get("needs_pattern_extraction", False)):
            pattern_cancel = threading.Event()
            _ignored, pattern_canceled = self.terminal.run_cancelable(
                "extracción de patrones",
                lambda: self._extract_patterns_from_turn(user_text, cancel_event=pattern_cancel),
                cancel_event=pattern_cancel,
            )
            if pattern_canceled:
                return False

        next_active = self._should_listen_for_followup(response, response_payload)
        if next_active:
            print("[HADES] Quedo activo para escuchar tu respuesta sin wake word. ESC cancela y vuelve a idle.")
        else:
            print("[HADES] Vuelvo a idle.")
        return next_active

    def _speak_cancelable(self, response: str) -> bool:
        cancel_event = threading.Event()
        _result, canceled = self.terminal.run_cancelable(
            "TTS",
            lambda: self.tts.speak(response, cancel_event=cancel_event),
            cancel_event=cancel_event,
        )
        return not canceled

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
- Si el usuario pide un recordatorio "X minutos antes" pero NO especifica claramente la hora del evento futuro, NO inventés hora. Hacé una sola pregunta concreta: "¿A qué hora querés que te lo recuerde?" o "¿A qué hora es el evento?".
- Si el usuario menciona una hora actual, por ejemplo "ahora son las 10:30", esa hora NO es automáticamente la hora del evento. Si además pide "30 minutos antes" y falta la hora del evento, preguntá.
- No cambiés la intención del usuario: "ir a comer" significa salir/ir a comer, NO preparar ni cocinar, salvo que el usuario diga explícitamente "cocinar", "preparar" o "hacer comida".
- Si el usuario pide editar, cambiar, modificar, mover, cancelar o eliminar una alarma/recordatorio, tratá eso como modificación/cancelación de una acción simulada anterior. Si está claro qué alarma/recordatorio y cuál es el nuevo valor, confirmá y registrá con type "alarm_update", "alarm_cancel", "reminder_update" o "reminder_cancel". Si falta cuál alarma o la nueva hora, hacé una sola pregunta concreta.
- Si el usuario pide "olvida eso", "borra el último patrón" o "borra la última acción", entendé que quiere corregir la memoria reciente. No lo conviertas en patrón; confirmá brevemente la corrección si ya fue manejada por reglas determinísticas.
- Si el usuario pide editar/cancelar "la alarma" y hay varias alarmas posibles en memoria, no adivinés: listá todas las opciones de alarma disponibles y pedí que elija por número u hora.
- Los recordatorios de pastillas, medicamentos o vitaminas son del dominio "health". No los dupliqués como "home" y "health". HADES solo registra recordatorios; no da consejos médicos ni cambia dosis.
- Si el usuario repite varias veces una frase de rutina parecida, por ejemplo "voy a dormir a las 10", "me voy a dormir a las 10" o "duermo a las 10", eso puede contar como señal de patrón aunque no diga explícitamente "normalmente". En ese caso needs_pattern_extraction debe ser true.
- Si hay ambigüedad práctica real, preguntá una sola vez. No rellenés huecos con memoria vieja ni con suposiciones.
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

    def _extract_patterns_from_turn(self, user_text: str, cancel_event: threading.Event | None = None) -> None:
        cancel_event = cancel_event or threading.Event()
        if cancel_event.is_set():
            return
        # Importante: patrones solo desde lo que dijo el usuario, no desde la respuesta de HADES.
        # Usamos los últimos turnos del usuario para que rutinas partidas en 2-3 frases
        # puedan extraerse sin mezclar sugerencias de HADES como evidencia.
        recent_user_lines = [
            str(turn.get("user", "")).strip()
            for turn in self.memory_manager.recent_conversation_history(limit=3)
            if isinstance(turn, dict) and str(turn.get("user", "")).strip()
        ]
        if not recent_user_lines or self._normalize(recent_user_lines[-1]) != self._normalize(user_text):
            recent_user_lines.append(user_text)

        transcript = "\n".join(f"Usuario: {line}" for line in recent_user_lines[-3:])

        try:
            extraction = self.extractor.extract(transcript)
            if cancel_event.is_set():
                return
            self.memory_manager.merge_extracted_patterns(extraction)
        except Exception as exc:
            print(f"[PatternExtractor] No se pudo actualizar memoria desde este turno: {exc}")


    def _handle_deterministic_memory_or_action_command(self, user_text: str, source: str) -> bool | None:
        """Maneja comandos que conviene resolver sin pasar por el LLM.

        Incluye:
        - "olvida eso", "borra el último patrón", "borra la última acción".
        - edición/cancelación ambigua de alarmas, listando todas las opciones disponibles.
        Devuelve None si no manejó nada; si maneja, devuelve si debe quedar activo.
        """
        normalized = self._normalize(user_text)

        if self.pending_action_choice:
            response, listen = self._resolve_pending_action_choice(user_text)
            self._emit_deterministic_response(user_text, response, source)
            return listen

        forget_response = self._handle_forget_command(normalized)
        if forget_response:
            self._emit_deterministic_response(user_text, forget_response, source)
            return False

        alarm_response = self._handle_alarm_reference_command(user_text, normalized)
        if alarm_response:
            response, listen = alarm_response
            self._emit_deterministic_response(user_text, response, source)
            return listen

        return None

    def _emit_deterministic_response(self, user_text: str, response: str, source: str) -> None:
        print(f"HADES: {response}")
        self._speak_cancelable(response)
        self.memory_manager.append_conversation_turn(
            user_text=user_text,
            assistant_text=response,
            source=source,
        )
        if response:
            print("[HADES] " + ("Quedo activo para escuchar tu respuesta sin wake word. ESC cancela y vuelve a idle." if self.pending_action_choice else "Vuelvo a idle."))

    @classmethod
    def _is_forget_command(cls, normalized: str) -> bool:
        forget_cues = [
            "olvida eso", "olvidalo", "olvida lo ultimo", "olvida lo ultimo que guardaste",
            "borra eso", "borra lo ultimo", "elimina eso", "quita eso", "deshaz eso", "deshace eso",
            "borra el ultimo patron", "borra ultimo patron", "olvida el ultimo patron",
            "borra la ultima accion", "borra ultima accion", "olvida la ultima accion",
            "borra la ultima alarma", "borra el ultimo recordatorio",
        ]
        return any(cls._normalize(cue) in normalized for cue in forget_cues)

    def _handle_forget_command(self, normalized: str) -> str | None:
        if not self._is_forget_command(normalized):
            return None

        wants_pattern = any(term in normalized for term in ["patron", "patrón", "rutina", "habito", "hábito"])
        wants_action = any(term in normalized for term in ["accion", "acción", "alarma", "recordatorio", "luz", "musica", "música"])

        if wants_pattern and not wants_action:
            removed = self.memory_manager.remove_last_pattern()
            if not removed:
                return "No encontré ningún patrón guardado para borrar."
            summary = self._summarize_pattern(removed)
            return f"Listo, borré el último patrón guardado: {summary}"

        if wants_action and not wants_pattern:
            removed = self.memory_manager.remove_last_action()
            if not removed:
                return "No encontré ninguna acción guardada para borrar."
            summary = self._summarize_action(removed)
            return f"Listo, borré la última acción guardada: {summary}"

        removed_item = self.memory_manager.remove_last_memory_item()
        if not removed_item:
            return "No encontré acciones ni patrones recientes para borrar."
        kind, item = removed_item
        if kind == "pattern":
            return f"Listo, borré el último patrón guardado: {self._summarize_pattern(item)}"
        return f"Listo, borré la última acción guardada: {self._summarize_action(item)}"

    @staticmethod
    def _summarize_action(action: dict[str, Any]) -> str:
        description = str(action.get("description", "")).strip()
        trigger = str(action.get("trigger_or_condition", "")).strip()
        action_type = str(action.get("type", "acción")).strip()
        if description:
            return description[:160]
        if trigger:
            return trigger[:160]
        return action_type or "acción"

    @staticmethod
    def _summarize_pattern(pattern: dict[str, Any]) -> str:
        normal = str(pattern.get("normal_behavior", "")).strip()
        evidence = str(pattern.get("evidence", "")).strip()
        domain = str(pattern.get("domain", "patrón")).strip()
        if normal:
            return normal[:160]
        if evidence:
            return evidence[:160]
        return domain or "patrón"

    @classmethod
    def _is_alarm_reference_command(cls, normalized: str) -> bool:
        if not any(cls._contains_whole_phrase(normalized, term) for term in ["alarma", "alarmas"]):
            return False
        return any(cls._contains_whole_phrase(normalized, term) for term in [
            "edita", "editar", "modifica", "modificar", "cambia", "cambiar", "mueve", "mover",
            "actualiza", "actualizar", "cancela", "cancelar", "elimina", "eliminar", "quita", "quitar", "borra", "borrar",
        ])

    @classmethod
    def _is_cancel_alarm_command(cls, normalized: str) -> bool:
        return any(cls._contains_whole_phrase(normalized, term) for term in [
            "cancela", "cancelar", "elimina", "eliminar", "quita", "quitar", "borra", "borrar",
        ])

    @classmethod
    def _is_edit_alarm_command(cls, normalized: str) -> bool:
        return any(cls._contains_whole_phrase(normalized, term) for term in [
            "edita", "editar", "modifica", "modificar", "cambia", "cambiar", "mueve", "mover", "actualiza", "actualizar",
        ])

    def _handle_alarm_reference_command(self, user_text: str, normalized: str) -> tuple[str, bool] | None:
        if not self._is_alarm_reference_command(normalized):
            return None

        alarms = self._list_alarm_options()
        if not alarms:
            return "No encontré alarmas guardadas para editar o cancelar.", False

        operation = "cancel" if self._is_cancel_alarm_command(normalized) else "edit"
        old_time, new_time = self._extract_alarm_edit_times(normalized)
        matched = self._match_alarm_option(alarms, old_time or self._single_time_if_only_reference(normalized))

        if matched and operation == "cancel":
            response = self._simulate_alarm_cancel(matched, user_text)
            return response, False

        if matched and operation == "edit" and new_time:
            response = self._simulate_alarm_update(matched, new_time, user_text)
            return response, False

        if matched and operation == "edit" and not new_time:
            self.pending_action_choice = {
                "kind": "alarm_edit_new_time",
                "operation": "edit",
                "options": [matched],
                "selected": matched,
            }
            return f"¿A qué hora querés mover la alarma {self._format_alarm_option(matched)}?", True

        if len(alarms) == 1:
            only = alarms[0]
            if operation == "cancel":
                response = self._simulate_alarm_cancel(only, user_text)
                return response, False
            self.pending_action_choice = {
                "kind": "alarm_edit_new_time",
                "operation": "edit",
                "options": [only],
                "selected": only,
            }
            return f"Solo encontré una alarma: {self._format_alarm_option(only)}. ¿A qué hora querés moverla?", True

        self.pending_action_choice = {
            "kind": "alarm_select",
            "operation": operation,
            "options": alarms,
            "new_time": new_time,
        }
        return self._alarm_disambiguation_question(alarms, operation, new_time), True

    def _resolve_pending_action_choice(self, user_text: str) -> tuple[str, bool]:
        pending = self.pending_action_choice or {}
        normalized = self._normalize(user_text)

        if self._is_negative_reply(normalized) or any(term in normalized for term in ["cancelar", "cancela", "dejalo", "déjalo"]):
            self.pending_action_choice = None
            return "Listo, no hago cambios.", False

        if pending.get("kind") == "alarm_edit_new_time":
            selected = pending.get("selected")
            new_time = self._single_time_if_only_reference(normalized)
            if not selected:
                self.pending_action_choice = None
                return "No pude identificar la alarma. No hice cambios.", False
            if not new_time:
                return "Necesito la nueva hora para editar esa alarma. ¿A qué hora querés moverla?", True
            self.pending_action_choice = None
            return self._simulate_alarm_update(selected, new_time, user_text), False

        if pending.get("kind") == "alarm_select":
            options = pending.get("options") or []
            operation = pending.get("operation") or "edit"
            new_time = pending.get("new_time")
            selected = self._select_option_from_reply(options, normalized)
            if not selected:
                return self._alarm_disambiguation_question(options, operation, new_time, prefix="No pude identificar cuál. "), True

            if operation == "cancel":
                self.pending_action_choice = None
                return self._simulate_alarm_cancel(selected, user_text), False

            if new_time:
                self.pending_action_choice = None
                return self._simulate_alarm_update(selected, new_time, user_text), False

            self.pending_action_choice = {
                "kind": "alarm_edit_new_time",
                "operation": "edit",
                "options": [selected],
                "selected": selected,
            }
            return f"¿A qué hora querés mover la alarma {self._format_alarm_option(selected)}?", True

        self.pending_action_choice = None
        return "No pude resolver esa selección. No hice cambios.", False

    def _list_alarm_options(self) -> list[dict[str, Any]]:
        # Se listan alarmas base y actualizaciones previas como opciones visibles.
        raw = self.memory_manager.list_actions(action_types={"alarm", "alarm_update"}, limit=12, include_rejected=False)
        options: list[dict[str, Any]] = []
        for action in raw:
            status = str(action.get("status", "")).lower()
            if status in {"rejected", "canceled", "cancelled"}:
                continue
            text = self._normalize(self._summarize_action(action))
            if any(term in text for term in ["cancelada", "cancelado", "eliminada", "eliminado"]):
                continue
            options.append(action)
        return options

    def _alarm_disambiguation_question(
        self,
        alarms: list[dict[str, Any]],
        operation: str,
        new_time: str | None = None,
        prefix: str = "",
    ) -> str:
        verb = "cancelar" if operation == "cancel" else "editar"
        suffix = f" hacia {new_time}" if operation == "edit" and new_time else ""
        lines = [f"{prefix}Encontré varias alarmas. ¿Cuál querés {verb}{suffix}?"]
        for idx, alarm in enumerate(alarms, start=1):
            lines.append(f"{idx}. {self._format_alarm_option(alarm)}")
        lines.append("Respondé con el número o con la hora de la alarma.")
        return "\n".join(lines)

    def _format_alarm_option(self, action: dict[str, Any]) -> str:
        text = self._summarize_action(action)
        created = str(action.get("created_at", "")).strip()
        created_suffix = f" ({created})" if created else ""
        return f"{text}{created_suffix}"

    @classmethod
    def _single_time_if_only_reference(cls, normalized: str) -> str | None:
        times = cls._extract_times_from_text(normalized)
        if len(times) == 1:
            return times[0]
        return None

    @classmethod
    def _extract_alarm_edit_times(cls, normalized: str) -> tuple[str | None, str | None]:
        """Extrae hora origen y destino para frases como 'cambia la alarma de las 7 a las 8'."""
        times = cls._extract_times_from_text(normalized)
        if len(times) >= 2:
            return times[0], times[1]
        if len(times) == 1:
            # Si usa 'a las' sin 'de las', usualmente solo está dando la nueva hora o la hora de referencia.
            return times[0], None
        return None, None

    @classmethod
    def _extract_times_from_text(cls, normalized: str) -> list[str]:
        word_to_hour = {
            "una": "1", "uno": "1", "dos": "2", "tres": "3", "cuatro": "4",
            "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9",
            "diez": "10", "once": "11", "doce": "12",
        }
        times: list[str] = []

        for match in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.?m\.?|p\.?m\.?)?\b", normalized):
            hour = int(match.group(1))
            minute = match.group(2) or "00"
            suffix = cls._suffix_from_context(normalized, match.group(3))
            times.append(f"{hour}:{minute}{suffix}".strip())

        # Evitar duplicar palabras si ya hubo número.
        for word, value in word_to_hour.items():
            if re.search(rf"\b{word}\b", normalized):
                minute = "30" if any(term in normalized for term in ["media", "treinta"]) else "00"
                suffix = cls._suffix_from_context(normalized, None)
                canonical = f"{int(value)}:{minute}{suffix}".strip()
                if canonical not in times:
                    times.append(canonical)

        return times

    @staticmethod
    def _suffix_from_context(normalized: str, explicit_suffix: str | None) -> str:
        if explicit_suffix:
            explicit_suffix = explicit_suffix.replace(".", "").lower()
            return " PM" if "p" in explicit_suffix else " AM"
        if any(term in normalized for term in ["noche", "tarde", "pm"]):
            return " PM"
        if any(term in normalized for term in ["manana", "mañana", "am"]):
            return " AM"
        return ""

    def _match_alarm_option(self, alarms: list[dict[str, Any]], target_time: str | None) -> dict[str, Any] | None:
        if not target_time:
            return None
        matches = []
        for alarm in alarms:
            # No usamos json.dumps(alarm) porque created_at contiene números que parecen horas.
            text = self._normalize(" ".join(
                str(alarm.get(key, ""))
                for key in ["description", "trigger_or_condition", "evidence", "meaning"]
            ))
            alarm_times = self._extract_times_from_text(text)
            if any(self._time_matches(target_time, alarm_time) for alarm_time in alarm_times):
                matches.append(alarm)
        return matches[0] if len(matches) == 1 else None

    def _select_option_from_reply(self, options: list[dict[str, Any]], normalized: str) -> dict[str, Any] | None:
        number = re.search(r"\b(\d{1,2})\b", normalized)
        if number:
            idx = int(number.group(1)) - 1
            if 0 <= idx < len(options):
                return options[idx]

        ordinal_map = {
            "primera": 0, "primero": 0, "uno": 0, "una": 0,
            "segunda": 1, "segundo": 1, "dos": 1,
            "tercera": 2, "tercero": 2, "tres": 2,
            "cuarta": 3, "cuarto": 3, "cuatro": 3,
        }
        for word, idx in ordinal_map.items():
            if self._contains_whole_phrase(normalized, word) and 0 <= idx < len(options):
                return options[idx]

        target_time = self._single_time_if_only_reference(normalized)
        return self._match_alarm_option(options, target_time)

    @staticmethod
    def _time_parts(value: str) -> tuple[int, str, str] | None:
        normalized = HadesAssistant._normalize(value)
        match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", normalized)
        if not match:
            return None
        hour = int(match.group(1))
        minute = match.group(2) or "00"
        suffix = match.group(3) or ""
        return hour, minute, suffix

    @classmethod
    def _time_matches(cls, requested: str, candidate: str) -> bool:
        req = cls._time_parts(requested)
        cand = cls._time_parts(candidate)
        if not req or not cand:
            return cls._normalize(requested) in cls._normalize(candidate)
        req_hour, req_minute, req_suffix = req
        cand_hour, cand_minute, cand_suffix = cand
        if req_hour != cand_hour or req_minute != cand_minute:
            return False
        # Si el usuario no dijo AM/PM, se acepta cualquier alarma con esa hora.
        if not req_suffix:
            return True
        return req_suffix == cand_suffix

    def _simulate_alarm_cancel(self, alarm: dict[str, Any], evidence: str) -> str:
        index = alarm.get("_memory_index")
        if isinstance(index, int):
            self.memory_manager.update_action_at_index(
                index,
                {
                    "status": "simulated",
                    "description": f"Alarma cancelada: {self._summarize_action(alarm)}",
                    "canceled_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        self.memory_manager.append_action(
            {
                "type": "alarm_cancel",
                "domain": "sleep",
                "status": "simulated",
                "description": f"Cancelación simulada de alarma: {self._summarize_action(alarm)}",
                "trigger_or_condition": evidence,
                "meaning": "El usuario pidió cancelar una alarma guardada.",
                "importance": "medium",
                "confidence": "high",
                "evidence": evidence,
            }
        )
        return f"Listo, cancelé de forma simulada la alarma: {self._summarize_action(alarm)}"

    def _simulate_alarm_update(self, alarm: dict[str, Any], new_time: str, evidence: str) -> str:
        index = alarm.get("_memory_index")
        original_summary = self._summarize_action(alarm)
        if isinstance(index, int):
            self.memory_manager.update_action_at_index(
                index,
                {
                    "status": "simulated",
                    "description": f"Alarma editada hacia {new_time}: {original_summary}",
                    "updated_to": new_time,
                },
            )
        self.memory_manager.append_action(
            {
                "type": "alarm_update",
                "domain": "sleep",
                "status": "simulated",
                "description": f"Edición simulada de alarma hacia {new_time}: {original_summary}",
                "trigger_or_condition": evidence,
                "meaning": "El usuario pidió editar una alarma guardada.",
                "importance": "medium",
                "confidence": "high",
                "evidence": evidence,
            }
        )
        return f"Listo, edité de forma simulada esa alarma para {new_time}."

    def _resolve_pending_action_if_needed(self, user_text: str) -> str | None:
        if not self.memory_manager.has_pending_action(max_age_minutes=10):
            return None

        normalized = self._normalize(user_text)

        # Si el usuario da un comando nuevo claro, ese comando manda sobre acciones
        # propuestas anteriormente. Esto evita que "siete" se lea como "sí" y
        # que una propuesta vieja contamine una alarma nueva.
        if self._looks_like_new_command(normalized):
            return None

        accepted = self._is_affirmative_reply(normalized)
        rejected = self._is_negative_reply(normalized)

        if accepted:
            self.memory_manager.update_last_proposed_action("accepted", note=user_text, max_age_minutes=10)
            return "El usuario aceptó la última acción propuesta. Ahora HADES debe concretar la ayuda de forma útil."

        if rejected:
            self.memory_manager.update_last_proposed_action("rejected", note=user_text, max_age_minutes=10)
            return "El usuario rechazó la última acción propuesta. HADES debe respetar la decisión y no insistir."

        return None

    @staticmethod
    def _contains_whole_phrase(text: str, phrase: str) -> bool:
        escaped = re.escape(HadesAssistant._normalize(phrase))
        return bool(re.search(rf"(?<!\w){escaped}(?!\w)", text))

    @classmethod
    def _is_affirmative_reply(cls, normalized: str) -> bool:
        words = normalized.split()
        phrases = [
            "si", "dale", "ok", "okay", "hagamoslo", "de acuerdo",
            "acepto", "claro", "correcto", "esta bien", "sí",
        ]
        return len(words) <= 5 and any(cls._contains_whole_phrase(normalized, phrase) for phrase in phrases)

    @classmethod
    def _is_negative_reply(cls, normalized: str) -> bool:
        words = normalized.split()
        strong_phrases = [
            "mejor no", "cancelar", "cancela", "rechazo", "dejalo",
            "dejalo asi", "no hace falta", "asi esta bien", "déjalo",
        ]
        if any(cls._contains_whole_phrase(normalized, phrase) for phrase in strong_phrases):
            return True
        return len(words) <= 5 and cls._contains_whole_phrase(normalized, "no")

    @classmethod
    def _looks_like_new_command(cls, normalized: str) -> bool:
        """Detecta comandos nuevos para no resolver una acción pendiente por accidente."""
        reuse_cues = ["igual que antes", "como siempre", "la misma", "el mismo", "lo mismo"]
        if any(cue in normalized for cue in reuse_cues):
            return False

        command_cues = [
            "pon", "ponme", "pone", "poneme", "poner", "crea", "creame",
            "activa", "activar", "enciende", "encende", "prende", "prender",
            "apaga", "apagar", "edita", "editar", "modifica", "modificar",
            "cambia", "cambiar", "mueve", "mover", "actualiza", "actualizar",
            "quita", "quitar", "elimina", "eliminar", "cancela", "cancelar",
            "recordame", "recuerdame", "avisame", "avisa", "despertame",
            "alarma", "arma", "recordatorio", "luz", "luces", "musica", "no molestar",
        ]
        temporal_cues = [
            "hoy", "ahora", "esta noche", "en la noche", "esta tarde",
            "mas tarde", "manana", "a las", "a la", "siete", "seis",
            "7", "6", "pm", "am",
        ]

        has_command = any(cls._contains_whole_phrase(normalized, cue) for cue in command_cues)
        has_temporal = any(cls._contains_whole_phrase(normalized, cue) for cue in temporal_cues)
        return has_command and (has_temporal or len(normalized.split()) > 5)

    @staticmethod
    def _relative_reminder_interval(normalized: str) -> str | None:
        """Devuelve el intervalo si el usuario pidió un recordatorio relativo: 30 minutos antes, media hora antes, etc."""
        if "antes" not in normalized:
            return None

        if "media hora antes" in normalized or "media hora" in normalized:
            return "media hora"

        match = re.search(
            r"\b(\d+|treinta|veinte|quince|diez|cinco)\s+(minuto|minutos)\s+antes\b",
            normalized,
        )
        if match:
            return f"{match.group(1)} minutos"

        return None

    @staticmethod
    def _has_explicit_event_time(normalized: str) -> bool:
        """Detecta si el usuario dio la hora del evento, no solo la hora actual."""
        patterns = [
            r"\ba\s+(la|las)\s+",      # a las 10, a la una
            r"\bpara\s+(la|las)\s+",  # para las 10
            r"\bel\s+evento\s+es\s+a\b",
            r"\bla\s+cita\s+es\s+a\b",
            r"\bla\s+reunion\s+es\s+a\b",
        ]
        return any(re.search(pattern, normalized) for pattern in patterns)

    @classmethod
    def _needs_relative_reminder_clarification(cls, normalized: str) -> tuple[bool, str | None]:
        interval = cls._relative_reminder_interval(normalized)
        if not interval:
            return False, None
        return not cls._has_explicit_event_time(normalized), interval

    @staticmethod
    def _action_text(action: dict[str, Any]) -> str:
        return HadesAssistant._normalize(
            " ".join(
                str(action.get(key, ""))
                for key in ["description", "trigger_or_condition", "meaning", "evidence", "domain", "type"]
            )
        )

    @staticmethod
    def _normalize_action_domain(action: dict[str, Any]) -> str:
        """Devuelve un único dominio canónico para evitar acciones duplicadas en varias áreas."""
        text = HadesAssistant._action_text(action)
        raw_domain = HadesAssistant._normalize(str(action.get("domain", "other")))

        medication_terms = [
            "pastilla", "pastillas", "medicina", "medicamento", "medicamentos",
            "vitamina", "vitaminas", "dosis", "tratamiento", "tomar la", "tomarme",
        ]
        if any(term in text for term in medication_terms):
            return "health"

        if any(term in text for term in ["dormir", "duermo", "duerma", "acostarme", "me acuesto", "despertar", "despertame"]):
            return "sleep"
        if any(term in text for term in ["trabajo", "trabajar", "laboral", "reunion", "reunión", "cliente"]):
            return "work"
        if any(term in text for term in ["estudio", "estudiar", "tarea", "examen", "universidad"]):
            return "study"
        if any(term in text for term in ["comer", "cena", "cenar", "almuerzo", "desayuno", "pasta", "comida"]):
            return "food"
        if any(term in text for term in ["musica", "música", "relajar", "descansar"]):
            return "relaxation"
        if any(term in text for term in ["luz", "luces", "casa", "cuarto", "sala", "no molestar"]):
            return "home"
        if any(term in text for term in ["cansado", "energia", "energía"]):
            return "energy"
        if any(term in text for term in ["estres", "estrés", "ansioso", "ánimo", "animo"]):
            return "emotional_state"

        # Si el modelo devolvió algo tipo "home | health" o "home, health", se escoge un solo dominio válido.
        for candidate in re.split(r"[|,/;]+", raw_domain):
            candidate = candidate.strip()
            if candidate in {"sleep", "study", "work", "food", "health", "relaxation", "home", "energy", "emotional_state", "other"}:
                return candidate
        return "other"

    @staticmethod
    def _normalize_action_type(action: dict[str, Any]) -> str:
        text = HadesAssistant._action_text(action)
        raw_type = HadesAssistant._normalize(str(action.get("type", "other")))

        is_edit = any(term in text for term in ["editar", "edita", "modificar", "modifica", "cambiar", "cambia", "mover", "mueve", "actualizar", "actualiza"])
        is_cancel = any(term in text for term in ["cancelar", "cancela", "eliminar", "elimina", "quitar", "quita", "borrar", "borra"])
        mentions_alarm = "alarma" in text or "despert" in text
        mentions_reminder = any(term in text for term in ["recordatorio", "recordame", "recuerdame", "avisame", "avisa"])

        if is_cancel and mentions_alarm:
            return "alarm_cancel"
        if is_cancel and mentions_reminder:
            return "reminder_cancel"
        if is_edit and mentions_alarm:
            return "alarm_update"
        if is_edit and mentions_reminder:
            return "reminder_update"

        allowed = {
            "suggestion", "reminder", "alarm", "alarm_update", "alarm_cancel",
            "reminder_update", "reminder_cancel", "planning", "question",
            "routine_adjustment", "music", "light", "do_not_disturb", "note", "other",
        }
        return raw_type if raw_type in allowed else "other"

    @staticmethod
    def _sanitize_actions(actions: Any) -> list[dict[str, Any]]:
        """Filtra acciones vagas, normaliza dominio/tipo y evita duplicados por área."""
        if not isinstance(actions, list):
            return []
        clean: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        allowed_status = {"proposed", "accepted", "rejected", "simulated"}

        for action in actions:
            if not isinstance(action, dict):
                continue
            action = dict(action)
            description = str(action.get("description", "")).strip()
            evidence = str(action.get("evidence", "")).strip()
            if not description or not evidence:
                continue

            action_type = HadesAssistant._normalize_action_type(action)
            # Las preguntas ya quedan en conversation_history.
            if action_type == "question":
                continue
            action["type"] = action_type
            action["domain"] = HadesAssistant._normalize_action_domain(action)

            status = str(action.get("status", "proposed")).strip().lower()
            if status not in allowed_status:
                status = "proposed"
            action["status"] = status
            action["importance"] = str(action.get("importance", "low")).strip().lower() or "low"
            action["confidence"] = str(action.get("confidence", "medium")).strip().lower() or "medium"

            # Evita que el LLM registre la misma acción dos veces en dominios distintos
            # (ej. pastillas como home y health). El dominio ya fue normalizado antes.
            key_text = HadesAssistant._normalize(evidence or description)
            key_text = re.sub(r"\s+", " ", key_text)
            key = (action_type, key_text[:120])
            if key in seen:
                continue
            seen.add(key)
            clean.append(action)
        return clean[:3]

    @staticmethod
    def _apply_temporal_safety_corrections(payload: dict[str, Any], user_text: str) -> dict[str, Any]:
        """Corrige errores peligrosos de AM/PM y recurrencia causados por memoria previa."""
        normalized = HadesAssistant._normalize(user_text)

        needs_relative_clarification, relative_interval = HadesAssistant._needs_relative_reminder_clarification(normalized)
        mentions_go_eat = any(term in normalized for term in ["ir a comer", "salir a comer", "voy a comer", "quiero ir a comer"])
        mentions_cooking = any(term in normalized for term in ["cocinar", "preparar", "hacer comida", "hacer pasta"])

        if needs_relative_clarification:
            if mentions_go_eat:
                question = f"¿A qué hora querés ir a comer para recordártelo {relative_interval} antes?"
            else:
                question = f"¿A qué hora es eso para recordártelo {relative_interval} antes?"
            return {
                "response": question,
                "proposed_actions": [],
                "needs_pattern_extraction": False,
                "listen_for_followup": True,
            }

        mentions_night = any(term in normalized for term in ["noche", "esta noche", "en la noche"])
        mentions_afternoon = any(term in normalized for term in ["tarde", "esta tarde"])
        mentions_seven = bool(re.search(r"\b(7|siete)\b", normalized))
        mentions_six = bool(re.search(r"\b(6|seis)\b", normalized))
        mentions_one_off = any(
            term in normalized
            for term in ["hoy", "ahora", "esta noche", "en la noche", "esta tarde", "mas tarde", "más tarde"]
        )

        mentions_recurring = any(
            term in normalized
            for term in [
                "todos los dias", "todos los días", "dias laborales", "días laborales",
                "lunes a viernes", "cada dia", "cada día", "siempre", "diario", "diaria",
            ]
        )

        target_pm: str | None = None
        if (mentions_night or mentions_afternoon) and mentions_seven:
            target_pm = "7:00 PM"
        elif mentions_afternoon and mentions_six:
            target_pm = "6:00 PM"

        def fix_text(value: Any) -> Any:
            if not isinstance(value, str):
                return value

            fixed = value

            if target_pm == "7:00 PM":
                fixed = re.sub(r"\b7(?::00)?\s*(a\.?\s*m\.?|AM)\b", "7:00 PM", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bsiete\s+de\s+la\s+mañana\b", "siete de la noche", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\b7\s+de\s+la\s+mañana\b", "7:00 PM", fixed, flags=re.IGNORECASE)
                fixed = fixed.replace("7:00 AM", "7:00 PM").replace("7 AM", "7:00 PM")
            elif target_pm == "6:00 PM":
                fixed = re.sub(r"\b6(?::00)?\s*(a\.?\s*m\.?|AM)\b", "6:00 PM", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\bseis\s+de\s+la\s+mañana\b", "seis de la tarde", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\b6\s+de\s+la\s+mañana\b", "6:00 PM", fixed, flags=re.IGNORECASE)
                fixed = fixed.replace("6:00 AM", "6:00 PM").replace("6 AM", "6:00 PM")

            # No cambiar la intención del usuario: "ir a comer" no es "preparar/cocinar".
            if mentions_go_eat and not mentions_cooking:
                fixed = re.sub(r"\b(comiences?\s+a\s+)?preparar\s+la\s+pasta\b", "vayas a comer pasta", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\b(cocinar|preparar)\b", "ir a comer", fixed, flags=re.IGNORECASE)

            # Si el comando actual dice hoy/ahora/esta noche y no trae recurrencia explícita,
            # limpiamos recurrencias heredadas de memoria previa.
            if mentions_one_off and not mentions_recurring:
                fixed = re.sub(r"\b(todos los días laborales|todos los dias laborales|d[ií]as laborales|lunes a viernes)\b", "hoy", fixed, flags=re.IGNORECASE)
                fixed = re.sub(r"\b(diaria|diario|diariamente|recurrente|todos los días|todos los dias)\b", "puntual", fixed, flags=re.IGNORECASE)

            return fixed

        payload["response"] = fix_text(payload.get("response", ""))

        for action in payload.get("proposed_actions", []) or []:
            if isinstance(action, dict):
                for key in ["description", "trigger_or_condition", "meaning", "evidence"]:
                    action[key] = fix_text(action.get(key, ""))

                if mentions_one_off and not mentions_recurring:
                    action["status"] = "simulated"
                    if str(action.get("confidence", "")).lower() == "high":
                        action["confidence"] = "medium"

        if mentions_one_off and not mentions_recurring:
            payload["needs_pattern_extraction"] = False
            payload["listen_for_followup"] = False

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

        mentions_edit_action = any(
            cue in normalized
            for cue in ["editar", "edita", "modificar", "modifica", "cambiar", "cambia", "mover", "mueve", "actualizar", "actualiza", "cancelar", "cancela", "eliminar", "elimina", "quitar", "quita"]
        )

        if mentions_alarm:
            hints.append("El usuario probablemente está pidiendo una alarma o recordatorio.")

        if mentions_edit_action and mentions_alarm:
            hints.append("El usuario está intentando editar/cancelar una alarma o recordatorio. Si está claro el objetivo y el nuevo valor, confirmá la modificación simulada; si no, preguntá una sola aclaración.")

        if mentions_night:
            hints.append("Si el usuario menciona 'noche' y una hora como 'siete', interpretá esa hora como PM: 7:00 PM / 19:00.")
        elif mentions_afternoon:
            hints.append("Si el usuario menciona 'tarde' y una hora como seis/siete, interpretá esa hora como PM.")
        elif mentions_morning:
            hints.append("Si el usuario menciona 'mañana' como parte del día y una hora, interpretá esa hora como AM.")

        if mentions_one_off and not mentions_recurring:
            hints.append("La frase suena a acción puntual de hoy/esta noche; no la conviertas en rutina recurrente.")

        relative_needs_clarification, relative_interval = HadesAssistant._needs_relative_reminder_clarification(normalized)
        if relative_needs_clarification:
            hints.append(
                f"El usuario pidió un recordatorio {relative_interval} antes, pero no dio una hora clara del evento. No inventés la hora; preguntá una sola aclaración."
            )

        if "ir a comer" in normalized or "salir a comer" in normalized:
            hints.append("No cambies 'ir a comer' por 'preparar comida'. Solo hablá de cocinar si el usuario lo dijo explícitamente.")

        if mentions_recurring:
            hints.append("La frase indica recurrencia; puede ser rutina si también hay horario o hábito claro.")

        return "\n".join(f"- {hint}" for hint in hints) if hints else "Sin pista especial; seguí el comando actual literal."
    @staticmethod
    def _canonical_hour_from_text(normalized: str) -> str | None:
        word_to_hour = {
            "una": "1", "uno": "1", "dos": "2", "tres": "3", "cuatro": "4",
            "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9",
            "diez": "10", "once": "11", "doce": "12",
        }
        match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\b", normalized)
        hour = None
        minute = "00"
        if match:
            hour = match.group(1)
            minute = match.group(2) or "00"
        else:
            for word, value in word_to_hour.items():
                if re.search(rf"\b{word}\b", normalized):
                    hour = value
                    break
            if hour and ("media" in normalized or "treinta" in normalized):
                minute = "30"

        if not hour:
            return None

        suffix = ""
        if any(term in normalized for term in ["noche", "tarde", "pm", "p.m"]):
            suffix = " PM"
        elif any(term in normalized for term in ["manana", "mañana", "am", "a.m"]):
            suffix = " AM"
        return f"{int(hour)}:{minute}{suffix}".strip()

    @classmethod
    def _routine_signature_from_text(cls, text: str) -> dict[str, str] | None:
        normalized = cls._normalize(text or "")
        hour = cls._canonical_hour_from_text(normalized)
        if not hour:
            return None

        if any(term in normalized for term in ["voy a dormir", "me voy a dormir", "me duermo", "duermo", "dormir", "me acuesto", "acostarme"]):
            return {
                "type": "routine",
                "domain": "sleep",
                "signature": f"sleep:{hour.lower()}",
                "normal_behavior": f"El usuario tiende a dormir o acostarse alrededor de las {hour}.",
                "trigger_or_condition": "Rutina nocturna inferida por repetición conversacional.",
                "meaning": "Puede servir para contextualizar alarmas, luces, modo no molestar o recordatorios nocturnos.",
            }

        if any(term in normalized for term in ["voy a estudiar", "estudio", "estudiar"]):
            return {
                "type": "routine",
                "domain": "study",
                "signature": f"study:{hour.lower()}",
                "normal_behavior": f"El usuario tiende a estudiar alrededor de las {hour}.",
                "trigger_or_condition": "Rutina de estudio inferida por repetición conversacional.",
                "meaning": "Puede servir para contextualizar recordatorios o bloques de estudio.",
            }

        if any(term in normalized for term in ["entro a trabajar", "trabajo a", "voy a trabajar", "empiezo a trabajar"]):
            return {
                "type": "routine",
                "domain": "work",
                "signature": f"work:{hour.lower()}",
                "normal_behavior": f"El usuario tiende a iniciar trabajo alrededor de las {hour}.",
                "trigger_or_condition": "Rutina laboral inferida por repetición conversacional.",
                "meaning": "Puede servir para contextualizar alarmas, recordatorios y organización diaria.",
            }

        if any(term in normalized for term in ["pastilla", "pastillas", "medicina", "medicamento", "vitamina"]):
            return {
                "type": "routine",
                "domain": "health",
                "signature": f"health-medication:{hour.lower()}",
                "normal_behavior": f"El usuario suele tomar pastillas, medicamentos o vitaminas alrededor de las {hour}.",
                "trigger_or_condition": "Recordatorio de salud inferido por repetición conversacional.",
                "meaning": "Puede servir únicamente para recordatorios; HADES no debe dar indicaciones médicas ni cambiar dosis.",
            }

        return None

    def _infer_repeated_patterns_from_history(self) -> None:
        """Consolida rutinas simples cuando el usuario repite la misma idea en varios turnos.

        Es deliberadamente conservador: requiere al menos dos menciones compatibles en los
        últimos turnos y solo cubre rutinas claras como dormir, estudiar, trabajo o pastillas.
        """
        try:
            history = self.memory_manager.recent_conversation_history(limit=10)
            buckets: dict[str, dict[str, Any]] = {}
            for turn in history:
                if not isinstance(turn, dict):
                    continue
                user_line = str(turn.get("user", "")).strip()
                if not user_line:
                    continue
                candidate = self._routine_signature_from_text(user_line)
                if not candidate:
                    continue
                signature = candidate["signature"]
                bucket = buckets.setdefault(signature, {"candidate": candidate, "examples": []})
                # Evitar contar la misma transcripción exacta repetida por error del STT dentro de la misma línea.
                if user_line not in bucket["examples"]:
                    bucket["examples"].append(user_line)

            for bucket in buckets.values():
                examples = bucket["examples"]
                if len(examples) < 2:
                    continue
                candidate = bucket["candidate"]

                memory = self.memory_manager.load_memory()
                existing_patterns = memory.get("user_profile", {}).get("patterns", [])
                combined_existing = self._normalize(json.dumps(existing_patterns, ensure_ascii=False))
                if self._normalize(candidate["signature"].split(":", 1)[-1]) in combined_existing and candidate["domain"] in combined_existing:
                    continue

                extraction = {
                    "profile_summary": "",
                    "patterns": [
                        {
                            "type": candidate["type"],
                            "domain": candidate["domain"],
                            "normal_behavior": candidate["normal_behavior"],
                            "trigger_or_condition": candidate["trigger_or_condition"],
                            "meaning": candidate["meaning"],
                            "importance": "medium" if candidate["domain"] in {"sleep", "work", "health"} else "low",
                            "flexibility": "medium",
                            "confidence": "medium",
                            "evidence": f"El usuario repitió varias veces: '{examples[0]}' / '{examples[1]}'",
                        }
                    ],
                    "open_questions": [],
                }
                self.memory_manager.merge_extracted_patterns(extraction)
        except Exception as exc:
            print(f"[PatternRepeater] No se pudo inferir patrón repetido: {exc}")

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
