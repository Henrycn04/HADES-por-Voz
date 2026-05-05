import json
import re
from typing import Any

from google import genai
from google.genai import types

from config.settings import Settings


class GeminiTextClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.gemini_api_key:
            self.client = genai.Client(api_key=settings.gemini_api_key)
        else:
            self.client = genai.Client()
        self.model = settings.text_model

    def generate_text(self, prompt: str, temperature: float = 0.4) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
            ),
        )
        return (response.text or "").strip()

    def generate_json(self, prompt: str, temperature: float = 0.2) -> dict[str, Any]:
        """
        Pide JSON a Gemini. Si el modelo devuelve markdown accidentalmente,
        intenta recuperar el bloque JSON.
        También maneja errores temporales como 503 por alta demanda.
        """
        import time
        from google.genai import errors

        last_error = None

        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        response_mime_type="application/json",
                    ),
                )

                text = (response.text or "").strip()
                return self._parse_json(text)

            except errors.ServerError as exc:
                last_error = exc
                print(f"[Gemini] Error temporal del servidor. Intento {attempt + 1}/3.")
                time.sleep(3)

            except Exception as exc:
                last_error = exc
                break

        raise RuntimeError(
            "Gemini no pudo completar la extracción en este momento. "
            "El modelo está saturado. Probá de nuevo en unos minutos."
        ) from last_error

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return json.loads(match.group(1).strip())

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])

        raise ValueError(f"No se pudo parsear JSON desde Gemini:\n{text}")
