import json
import re
import urllib.error
import urllib.request
from typing import Any

from config.settings import Settings


class OllamaTextClient:
    """
    Cliente mínimo para Ollama. Usa /api/generate para conversación y JSON.
    La configuración separa conversación natural de extracción estructurada.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model

    def generate_text(self, prompt: str, temperature: float | None = None) -> str:
        payload = self._base_payload(
            prompt=prompt,
            temperature=self.settings.ollama_conversation_temperature if temperature is None else temperature,
            num_predict=self.settings.ollama_conversation_num_predict,
        )
        data = self._post_json("/api/generate", payload)
        return (data.get("response") or "").strip()

    def generate_json(self, prompt: str, temperature: float | None = None) -> dict[str, Any]:
        payload = self._base_payload(
            prompt=prompt,
            temperature=self.settings.ollama_extraction_temperature if temperature is None else temperature,
            num_predict=self.settings.ollama_json_num_predict,
        )
        payload["format"] = "json"
        data = self._post_json("/api/generate", payload)
        text = (data.get("response") or "").strip()
        return self._parse_json(text)

    def _base_payload(self, prompt: str, temperature: float, num_predict: int) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": self.settings.ollama_think,
            "options": {
                "temperature": temperature,
                "top_k": self.settings.ollama_top_k,
                "top_p": self.settings.ollama_top_p,
                "num_ctx": self.settings.ollama_num_ctx,
                "num_predict": num_predict,
            },
        }

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "No pude conectar con Ollama. Revisá que Ollama esté abierto y que el modelo exista. "
                f"Modelo configurado: {self.model}. URL: {url}"
            ) from exc

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

        raise ValueError(f"No se pudo parsear JSON desde Ollama:\n{text}")
