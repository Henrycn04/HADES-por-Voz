from datetime import datetime
from pathlib import Path
import queue
import time
from collections import deque

import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper

from config.settings import Settings


class WhisperSTT:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.device_id = settings.audio_input_device_id
        self.sample_rate = settings.sample_rate
        self.record_seconds = settings.command_record_seconds
        self.language = settings.whisper_language
        self.audio_in_dir: Path = settings.audio_in_dir
        self.audio_in_dir.mkdir(parents=True, exist_ok=True)
        self._model = None

    def _load_model(self):
        if self._model is None:
            print(f"[Whisper] Cargando modelo: {self.settings.whisper_model}")
            self._model = whisper.load_model(self.settings.whisper_model)
        return self._model

    def record_command(self, seconds: int | None = None, prefix: str = "command") -> Path:
        seconds = seconds or self.record_seconds
        print(f"[STT] Grabando comando por {seconds} segundos...")
        recording = sd.rec(
            int(seconds * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            device=self.device_id,
        )
        sd.wait()

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_path = self.audio_in_dir / f"{prefix}_{stamp}.wav"
        sf.write(audio_path, recording, self.sample_rate)
        return audio_path

    def record_until_silence(self, prefix: str = "command") -> Path | None:
        """
        Graba sin duración fija usando callback, igual que el wake word.
        En algunos dispositivos de Windows, stream.read() puede devolver silencio,
        aunque el callback sí recibe audio real. Por eso usamos una cola de frames.
        """
        frame_seconds = 0.10
        frame_samples = int(self.sample_rate * frame_seconds)
        threshold = self.settings.voice_energy_threshold
        start_timeout = self.settings.command_start_timeout_seconds
        silence_timeout = self.settings.command_silence_timeout_seconds
        max_record = self.settings.command_max_record_seconds
        min_record = self.settings.command_min_record_seconds
        preroll_seconds = self.settings.command_preroll_seconds
        debug_energy = self.settings.stt_debug_energy

        audio_queue: queue.Queue[np.ndarray] = queue.Queue()

        def callback(indata, frames, time_info, status):
            if status:
                print(status)
            audio_queue.put(np.asarray(indata, dtype=np.float32).copy())

        chunks: list[np.ndarray] = []
        preroll_max_frames = max(1, int(preroll_seconds / frame_seconds))
        preroll = deque(maxlen=preroll_max_frames)
        started = False
        started_at: float | None = None
        last_voice_at: float | None = None
        wait_started_at = time.monotonic()
        last_debug_at = wait_started_at
        max_rms_seen = 0.0
        max_abs_seen = 0.0

        print(
            "[STT] Escuchando comando... "
            f"hablá con naturalidad; corto tras {silence_timeout:.1f}s de silencio."
        )

        with sd.InputStream(
            device=self.device_id,
            channels=1,
            samplerate=self.sample_rate,
            blocksize=frame_samples,
            dtype="float32",
            callback=callback,
        ):
            while True:
                try:
                    frame = audio_queue.get(timeout=0.25)
                except queue.Empty:
                    now = time.monotonic()
                    if not started and now - wait_started_at >= start_timeout:
                        print(
                            "[STT] No detecté voz. Volviendo a modo pasivo. "
                            f"Max RMS visto={max_rms_seen:.5f}, max_abs={max_abs_seen:.5f}, "
                            f"threshold={threshold:.5f}."
                        )
                        return None
                    continue

                frame = np.asarray(frame, dtype=np.float32)
                mono = frame[:, 0] if frame.ndim > 1 else frame
                rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
                max_abs = float(np.max(np.abs(mono))) if mono.size else 0.0
                now = time.monotonic()
                has_voice = rms >= threshold
                max_rms_seen = max(max_rms_seen, rms)
                max_abs_seen = max(max_abs_seen, max_abs)

                if not started:
                    preroll.append(frame)

                    if debug_energy and now - last_debug_at >= 0.8:
                        print(
                            f"[STT debug] rms={rms:.5f} max_rms={max_rms_seen:.5f} "
                            f"max_abs={max_abs_seen:.5f} threshold={threshold:.5f}"
                        )
                        last_debug_at = now

                    if has_voice:
                        started = True
                        started_at = now
                        last_voice_at = now
                        chunks.extend(list(preroll))
                        if debug_energy:
                            print(f"[STT debug] voz detectada rms={rms:.5f} max_abs={max_abs:.5f}")
                    elif now - wait_started_at >= start_timeout:
                        print(
                            "[STT] No detecté voz. Volviendo a modo pasivo. "
                            f"Max RMS visto={max_rms_seen:.5f}, max_abs={max_abs_seen:.5f}, "
                            f"threshold={threshold:.5f}."
                        )
                        return None
                    continue

                chunks.append(frame)

                if has_voice:
                    last_voice_at = now

                recorded_seconds = now - (started_at or now)
                silence_seconds = now - (last_voice_at or now)

                if recorded_seconds >= max_record:
                    print(f"[STT] Alcancé el máximo de grabación ({max_record:.1f}s).")
                    break

                if recorded_seconds >= min_record and silence_seconds >= silence_timeout:
                    break

        if not chunks:
            return None

        recording = np.concatenate(chunks, axis=0)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_path = self.audio_in_dir / f"{prefix}_{stamp}.wav"
        sf.write(audio_path, recording, self.sample_rate)
        if debug_energy:
            print(
                f"[STT debug] audio guardado={audio_path} frames={len(recording)} "
                f"max_rms={max_rms_seen:.5f} max_abs={max_abs_seen:.5f}"
            )
        return audio_path

    def transcribe(self, audio_path: Path) -> str:
        model = self._load_model()
        result = model.transcribe(
            str(audio_path),
            language=self.language,
            fp16=False,
        )
        return str(result.get("text", "")).strip()

    def listen_command(self, seconds: int | None = None) -> tuple[str, Path | None]:
        if seconds is None:
            audio_path = self.record_until_silence(prefix="wake_command")
            if audio_path is None:
                return "", None
        else:
            audio_path = self.record_command(seconds=seconds, prefix="wake_command")

        print("[STT] Transcribiendo...")
        text = self.transcribe(audio_path)
        return text, audio_path
