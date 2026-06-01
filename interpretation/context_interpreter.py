import json
from typing import Any

from agent.prompts import HADES_SYSTEM_STYLE, INTERPRETATION_SCHEMA


class ContextInterpreter:
    def __init__(self, llm: Any):
        self.llm = llm

    def interpret(self, memory: dict, current_context: str) -> dict:
        prompt = f"""
{HADES_SYSTEM_STYLE}

Tenés una memoria contextual del usuario y una situación actual.
Tu tarea es interpretar si la situación sigue un patrón normal o si hay una desviación significativa.

Idea central de HADES:
No solo importa saber qué hace normalmente la persona.
También importa entender qué puede significar cuando rompe un patrón.

Memoria del usuario:
{json.dumps(memory, indent=2, ensure_ascii=False)}

Situación actual:
{current_context}

Instrucciones:
- Compará la situación contra la memoria.
- Detectá señales de desviación.
- Generá hipótesis, no diagnósticos.
- La respuesta final debe sonar natural y útil, no robótica.
- Si no hay memoria suficiente, reconocelo y preguntá suavemente.

Formato requerido:
{INTERPRETATION_SCHEMA}
"""
        return self.llm.generate_json(prompt, temperature=0.1)
