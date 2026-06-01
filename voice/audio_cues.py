import math
from typing import Sequence

import numpy as np
import sounddevice as sd

from config.settings import Settings


class AudioCuePlayer:
    """Sonidos cortos para que el usuario sepa cuándo HADES escucha."""

    def __init__(self, settings: Settings):
        self.enabled = settings.enable_audio_cues
        self.output_device_id = settings.audio_output_device_id
        self.sample_rate = settings.cue_sample_rate
        self.volume = settings.cue_volume

    def passive_listening(self) -> None:
        """Cue mínimo cuando HADES vuelve a esperar wake word."""
        self._play_click(freq=900, duration=0.035)

    def wake_detected(self) -> None:
        """Click corto cuando la wake word activó al asistente."""
        self._play_click(freq=1200, duration=0.045)

    def followup_listening(self) -> None:
        """Click corto cuando HADES empieza a escuchar respuesta."""
        self._play_click(freq=1000, duration=0.035)
    def _play_click(self, freq: int = 1000, duration: float = 0.035) -> None:
        if not self.enabled:
            return
        try:
            n = max(1, int(self.sample_rate * duration))
            t = np.arange(n, dtype=np.float32) / float(self.sample_rate)

            # Click tipo "tuck": seno corto con caída rápida.
            wave = np.sin(2 * math.pi * float(freq) * t).astype(np.float32)
            envelope = np.exp(-45 * t).astype(np.float32)
            audio = wave * envelope * float(self.volume)

            sd.play(audio, samplerate=self.sample_rate, device=self.output_device_id)
            sd.wait()
        except Exception as exc:
            print(f"[AudioCue] No pude reproducir cue: {exc}")
    def _play_sequence(self, tones: Sequence[tuple[int, float]]) -> None:
        if not self.enabled:
            return
        try:
            chunks = []
            for freq, duration in tones:
                n = max(1, int(self.sample_rate * duration))
                if freq <= 0:
                    chunks.append(np.zeros(n, dtype=np.float32))
                    continue
                t = np.arange(n, dtype=np.float32) / float(self.sample_rate)
                wave = np.sin(2 * math.pi * float(freq) * t).astype(np.float32)
                # Fade in/out para evitar clicks.
                fade_n = min(int(self.sample_rate * 0.01), max(1, n // 3))
                if fade_n > 0:
                    fade = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
                    wave[:fade_n] *= fade
                    wave[-fade_n:] *= fade[::-1]
                chunks.append(wave * float(self.volume))
            audio = np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)
            if audio.size:
                sd.play(audio, samplerate=self.sample_rate, device=self.output_device_id)
                sd.wait()
        except Exception as exc:
            print(f"[AudioCue] No pude reproducir cue: {exc}")
