import platform
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from kokoro_onnx import Kokoro

from config.settings import Settings


class KokoroTTS:
    def __init__(self, settings: Settings):
        self.enabled = settings.enable_tts
        self.autoplay = settings.autoplay_tts
        self.output_device_id = settings.audio_output_device_id
        self.audio_dir: Path = settings.audio_dir
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self.model_path = settings.kokoro_model_path
        self.voices_path = settings.kokoro_voices_path
        self.voice = settings.kokoro_voice
        self.speed = settings.kokoro_speed
        self.lang = settings.kokoro_lang
        self._kokoro: Kokoro | None = None

    def _load(self) -> Kokoro:
        if self._kokoro is None:
            if not self.model_path.exists() or not self.voices_path.exists():
                raise FileNotFoundError(
                    "No encontré los archivos de Kokoro. Deben estar en:\n"
                    f"- {self.model_path}\n"
                    f"- {self.voices_path}"
                )
            self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
        return self._kokoro

    def speak(self, text: str, filename: str | None = None) -> Path | None:
        if not self.enabled or not text.strip():
            return None

        if filename is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"hades_response_{stamp}.wav"

        output_path = self.audio_dir / filename

        try:
            kokoro = self._load()
            audio, sample_rate = kokoro.create(
                text,
                voice=self.voice,
                speed=self.speed,
                lang=self.lang,
            )
            sf.write(output_path, audio, sample_rate)

            if self.autoplay:
                try:
                    self._play_audio_array(audio, sample_rate)
                except Exception as exc:
                    print(f"[KokoroTTS] No pude reproducir con sounddevice: {exc}")
                    print("[KokoroTTS] Intentando reproducir el WAV guardado...")
                    self._play_audio_file(output_path)
            else:
                print(f"[KokoroTTS] Audio guardado en: {output_path}")

            return output_path
        except Exception as exc:
            print(f"[KokoroTTS] No se pudo generar/reproducir audio. Error: {exc}")
            return None

    def _play_audio_array(self, audio, sample_rate: int) -> None:
        audio_np = np.asarray(audio, dtype=np.float32).squeeze()
        if audio_np.size == 0:
            return

        print("[KokoroTTS] Reproduciendo respuesta...")
        sd.play(audio_np, samplerate=sample_rate, device=self.output_device_id)
        sd.wait()

    @staticmethod
    def _play_audio_file(path: Path) -> None:
        system = platform.system().lower()

        if system == "windows":
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return

        if system == "darwin":
            subprocess.run(["afplay", str(path)], check=False)
            return

        for player in ("paplay", "aplay", "ffplay"):
            try:
                if player == "ffplay":
                    subprocess.run([player, "-nodisp", "-autoexit", str(path)], check=False)
                else:
                    subprocess.run([player, str(path)], check=False)
                return
            except FileNotFoundError:
                continue

        print(f"[KokoroTTS] Audio guardado en: {path}")
