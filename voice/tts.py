import base64
import os
import platform
import subprocess
import wave
from pathlib import Path

from google import genai
from google.genai import types

from config.settings import Settings


class GeminiTTS:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.enabled = settings.enable_tts
        self.autoplay = settings.autoplay_tts
        self.model = settings.tts_model
        self.voice = settings.tts_voice
        self.audio_dir = settings.audio_dir
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        if settings.gemini_api_key:
            self.client = genai.Client(api_key=settings.gemini_api_key)
        else:
            self.client = genai.Client()

    def speak(self, text: str, filename: str = "hades_response.wav") -> Path | None:
        """
        Genera un .wav usando Gemini TTS.
        El usuario todavía escribe por teclado; solo la salida del agente se habla.
        """
        if not self.enabled or not text.strip():
            return None

        output_path = self.audio_dir / filename

        try:
            prompt = (
                "Di el siguiente texto en español latino, con voz calmada, cercana, "
                "natural y ligeramente reflexiva, como un asistente doméstico útil:\n\n"
                f"{text}"
            )

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=self.voice,
                            )
                        )
                    ),
                ),
            )

            data = response.candidates[0].content.parts[0].inline_data.data

            # En Python normalmente viene como bytes; en otros entornos puede venir base64.
            if isinstance(data, str):
                data = base64.b64decode(data)

            self._write_wave(output_path, data)

            if self.autoplay:
                self._play_audio(output_path)

            return output_path

        except Exception as exc:
            print(f"[TTS] No se pudo generar/reproducir audio. El texto se mantiene en pantalla. Error: {exc}")
            return None

    @staticmethod
    def _write_wave(filename: Path, pcm: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2) -> None:
        with wave.open(str(filename), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(pcm)

    @staticmethod
    def _play_audio(path: Path) -> None:
        system = platform.system().lower()

        if system == "windows":
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return

        if system == "darwin":
            subprocess.run(["afplay", str(path)], check=False)
            return

        # Linux: intenta reproductores comunes.
        for player in ("paplay", "aplay", "ffplay"):
            try:
                if player == "ffplay":
                    subprocess.run([player, "-nodisp", "-autoexit", str(path)], check=False)
                else:
                    subprocess.run([player, str(path)], check=False)
                return
            except FileNotFoundError:
                continue

        print(f"[TTS] Audio guardado en: {path}")
