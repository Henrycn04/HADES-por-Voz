from agent.gemini_client import GeminiTextClient
from agent.prompts import HADES_SYSTEM_STYLE, PATTERN_EXTRACTION_SCHEMA


class PatternExtractor:
    def __init__(self, gemini: GeminiTextClient):
        self.gemini = gemini

    def extract(self, transcript: str) -> dict:
        prompt = f"""
{HADES_SYSTEM_STYLE}

Vas a analizar una conversación inicial entre HADES y el usuario.

Objetivo:
Extraer memoria contextual útil para un agente doméstico conversacional.
Buscá rutinas, preferencias, prioridades, excepciones, señales de intención e incertidumbres.

Importante:
- No inventés patrones.
- Si algo es ambiguo, bajá la confianza.
- Las excepciones importan tanto como las rutinas.
- La salida debe ser memoria útil para interpretar situaciones futuras.

Conversación:
{transcript}

Formato requerido:
{PATTERN_EXTRACTION_SCHEMA}
"""
        return self.gemini.generate_json(prompt)
