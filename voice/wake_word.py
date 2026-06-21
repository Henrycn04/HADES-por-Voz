import threading
import time

import numpy as np
import sounddevice as sd
import openwakeword
from openwakeword.model import Model

from config.settings import Settings


class WakeWordListener:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.device_id = settings.audio_input_device_id
        self.sample_rate = settings.sample_rate
        self.frame_ms = 80
        self.frame_samples = int(self.sample_rate * self.frame_ms / 1000)
        self.wake_word = settings.wake_word
        self.threshold = settings.wake_threshold
        self.cooldown_seconds = settings.wake_cooldown_seconds

        print(f"[WakeWord] Cargando modelo: {self.wake_word}")
        openwakeword.utils.download_models()
        self.model = Model(wakeword_models=[self.wake_word])

    def wait_for_wake_word(self, cancel_event: threading.Event | None = None) -> float | None:
        cancel_event = cancel_event or threading.Event()
        event = threading.Event()
        detected_score = {"value": 0.0}

        def callback(indata, frames, time_info, status):
            if status:
                print(status)

            if event.is_set() or cancel_event.is_set():
                return

            audio = (indata[:, 0] * 32767).astype(np.int16)
            prediction = self.model.predict(audio)
            score = float(prediction.get(self.wake_word, 0.0))

            if score >= self.threshold:
                detected_score["value"] = score
                event.set()

        with sd.InputStream(
            device=self.device_id,
            channels=1,
            samplerate=self.sample_rate,
            blocksize=self.frame_samples,
            dtype="float32",
            callback=callback,
        ):
            while not event.is_set() and not cancel_event.is_set():
                sd.sleep(100)

        if cancel_event.is_set() and not event.is_set():
            if hasattr(self.model, "reset"):
                self.model.reset()
            return None

        time.sleep(self.cooldown_seconds)
        if hasattr(self.model, "reset"):
            self.model.reset()

        return detected_score["value"]
