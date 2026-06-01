from typing import Any

from agent.prompts import HADES_SYSTEM_STYLE, PATTERN_EXTRACTION_SCHEMA


class PatternExtractor:
    def __init__(self, llm: Any):
        self.llm = llm

    def extract(self, transcript: str) -> dict:
        prompt = f"""
{HADES_SYSTEM_STYLE}

Vas a analizar SOLO lo que dijo el usuario para actualizar memoria contextual.

Objetivo:
Extraer memoria útil para un asistente doméstico que aprende rutinas y preferencias reales.

Reglas estrictas:
- La evidencia debe venir únicamente del usuario, no de HADES.
- Si el texto incluye líneas de HADES, ignóralas por completo.
- No guardés preguntas, sugerencias ni explicaciones hechas por HADES.
- No guardés estados momentáneos como patrones permanentes. Ejemplos: hambre actual, cansancio de hoy, una actividad de esta tarde.
- No guardés alarmas, recordatorios o tareas únicas como patrones; eso pertenece a action_history.
- PERO si una alarma, recordatorio o automatización es recurrente y revela una rutina estable, sí debés extraer el patrón de rutina además de la acción.
- Ejemplo: "despertame todos los días laborales a las 7 porque trabajo a las 9" debe generar patrones sobre despertarse a las 7 en días laborales y empezar a trabajar a las 9.
- Guardá patrones solo si hay señales de estabilidad: normalmente, suelo, siempre, prefiero, me gusta, no me gusta, cada día, todos los días, días laborales, lunes a viernes, los lunes, usualmente, tengo rutina de..., etc.
- Si solo hay un comando puntual, devolvé patterns: [] y open_questions: [].
- Máximo 2 patrones por turno.
- Máximo 1 open_question por turno, y solo si es realmente importante.
- Usá importance "high" solo para información claramente central o repetida. Ante duda, usá "low".
- La extracción debe ser literal y basada en evidencia textual del usuario.

Texto del usuario o transcripción:
{transcript}

Formato requerido:
{PATTERN_EXTRACTION_SCHEMA}
"""
        return self.llm.generate_json(prompt, temperature=0.1)
