import platform
import subprocess
import threading
import time
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

    def speak(self, text: str, filename: str | None = None, cancel_event: threading.Event | None = None) -> Path | None:
        cancel_event = cancel_event or threading.Event()
        if not self.enabled or not text.strip() or cancel_event.is_set():
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
            if cancel_event.is_set():
                return None
            sf.write(output_path, audio, sample_rate)

            if self.autoplay:
                try:
                    self._play_audio_array(audio, sample_rate, cancel_event=cancel_event)
                except Exception as exc:
                    print(f"[KokoroTTS] No pude reproducir con sounddevice: {exc}")
                    print("[KokoroTTS] Intentando reproducir el WAV guardado...")
                    self._play_audio_file(output_path, cancel_event=cancel_event)
            else:
                print(f"[KokoroTTS] Audio guardado en: {output_path}")

            return output_path
        except Exception as exc:
            print(f"[KokoroTTS] No se pudo generar/reproducir audio. Error: {exc}")
            return None

    def _play_audio_array(self, audio, sample_rate: int, cancel_event: threading.Event | None = None) -> None:
        cancel_event = cancel_event or threading.Event()
        audio_np = np.asarray(audio, dtype=np.float32).squeeze()
        if audio_np.size == 0 or cancel_event.is_set():
            return

        print("[KokoroTTS] Reproduciendo respuesta...")
        chunk_size = max(1, int(sample_rate * 0.10))
        with sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=self.output_device_id,
        ) as stream:
            for start in range(0, audio_np.size, chunk_size):
                if cancel_event.is_set():
                    sd.stop()
                    print("[KokoroTTS] Reproducción cancelada.")
                    return
                chunk = audio_np[start:start + chunk_size].reshape(-1, 1)
                stream.write(chunk)

    @staticmethod
    def _play_audio_file(path: Path, cancel_event: threading.Event | None = None) -> None:
        cancel_event = cancel_event or threading.Event()
        if cancel_event.is_set():
            return
        system = platform.system().lower()

        if system == "windows":
            import winsound
            duration = 0.0
            try:
                duration = float(sf.info(path).duration)
            except Exception:
                duration = 30.0
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            end_at = time.monotonic() + duration
            while time.monotonic() < end_at:
                if cancel_event.is_set():
                    winsound.PlaySound(None, winsound.SND_PURGE)
                    return
                time.sleep(0.05)
            return

        if system == "darwin":
            proc = subprocess.Popen(["afplay", str(path)])
            while proc.poll() is None:
                if cancel_event.is_set():
                    proc.terminate()
                    return
                time.sleep(0.05)
            return

        for player in ("paplay", "aplay", "ffplay"):
            try:
                cmd = [player, "-nodisp", "-autoexit", str(path)] if player == "ffplay" else [player, str(path)]
                proc = subprocess.Popen(cmd)
                while proc.poll() is None:
                    if cancel_event.is_set():
                        proc.terminate()
                        return
                    time.sleep(0.05)
                return
            except FileNotFoundError:
                continue

        print(f"[KokoroTTS] Audio guardado en: {path}")
