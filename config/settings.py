import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    base_dir: Path = Path(__file__).resolve().parents[1]

    # LLM provider. Por defecto usa Ollama/Gemma local.
    llm_provider: str = os.getenv("HADES_LLM_PROVIDER", "ollama").strip().lower()

    # Ollama / Gemma local.
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma4")
    ollama_think: bool = _env_bool("OLLAMA_THINK", False)
    ollama_num_ctx: int = _env_int("OLLAMA_NUM_CTX", 4096)
    ollama_top_k: int = _env_int("OLLAMA_TOP_K", 40)
    ollama_top_p: float = _env_float("OLLAMA_TOP_P", 0.9)
    ollama_conversation_temperature: float = _env_float("OLLAMA_CONVERSATION_TEMPERATURE", 0.4)
    ollama_extraction_temperature: float = _env_float("OLLAMA_EXTRACTION_TEMPERATURE", 0.1)
    ollama_conversation_num_predict: int = _env_int("OLLAMA_CONVERSATION_NUM_PREDICT", 300)
    ollama_json_num_predict: int = _env_int("OLLAMA_JSON_NUM_PREDICT", 700)

    # Gemini opcional como fallback.
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    text_model: str = os.getenv("HADES_TEXT_MODEL", "gemini-2.5-flash")
    tts_model: str = os.getenv("HADES_TTS_MODEL", "gemini-3.1-flash-tts-preview")
    tts_voice: str = os.getenv("HADES_TTS_VOICE", "Kore")

    # Voz / audio.
    enable_tts: bool = _env_bool("HADES_ENABLE_TTS", True)
    autoplay_tts: bool = _env_bool("HADES_AUTOPLAY_TTS", True)
    audio_input_device_id: int = _env_int("HADES_AUDIO_INPUT_DEVICE_ID", 11)
    audio_output_device_id: int | None = _env_optional_int("HADES_AUDIO_OUTPUT_DEVICE_ID")
    sample_rate: int = _env_int("HADES_SAMPLE_RATE", 16000)
    command_record_seconds: int = _env_int("HADES_COMMAND_RECORD_SECONDS", 5)
    command_start_timeout_seconds: float = _env_float("HADES_COMMAND_START_TIMEOUT_SECONDS", 10.0)
    command_silence_timeout_seconds: float = _env_float("HADES_COMMAND_SILENCE_TIMEOUT_SECONDS", 2.8)
    command_max_record_seconds: float = _env_float("HADES_COMMAND_MAX_RECORD_SECONDS", 20.0)
    command_min_record_seconds: float = _env_float("HADES_COMMAND_MIN_RECORD_SECONDS", 0.8)
    voice_energy_threshold: float = _env_float("HADES_VOICE_ENERGY_THRESHOLD", 0.004)
    command_preroll_seconds: float = _env_float("HADES_COMMAND_PREROLL_SECONDS", 0.35)
    stt_debug_energy: bool = _env_bool("HADES_STT_DEBUG_ENERGY", False)

    # Sonidos cortos de estado.
    enable_audio_cues: bool = _env_bool("HADES_ENABLE_AUDIO_CUES", True)
    cue_volume: float = _env_float("HADES_CUE_VOLUME", 0.16)
    cue_sample_rate: int = _env_int("HADES_CUE_SAMPLE_RATE", 16000)

    # Wake word. Para pruebas usamos modelo preentrenado. Luego se puede cambiar a HADES personalizado.
    wake_word: str = os.getenv("HADES_WAKE_WORD", "hey jarvis")
    wake_threshold: float = _env_float("HADES_WAKE_THRESHOLD", 0.85)
    wake_cooldown_seconds: float = _env_float("HADES_WAKE_COOLDOWN_SECONDS", 1.5)

    # Whisper STT.
    whisper_model: str = os.getenv("HADES_WHISPER_MODEL", "base")
    whisper_language: str = os.getenv("HADES_WHISPER_LANGUAGE", "Spanish")

    # Kokoro TTS.
    kokoro_model_path: Path = base_dir / os.getenv("KOKORO_MODEL_PATH", "models/kokoro/kokoro-v1.0.onnx")
    kokoro_voices_path: Path = base_dir / os.getenv("KOKORO_VOICES_PATH", "models/kokoro/voices-v1.0.bin")
    kokoro_voice: str = os.getenv("KOKORO_VOICE", "em_alex")
    kokoro_speed: float = _env_float("KOKORO_SPEED", 1.15)
    kokoro_lang: str = os.getenv("KOKORO_LANG", "es")

    # Directorios.
    memory_dir: Path = base_dir / "memory"
    logs_dir: Path = base_dir / "data" / "conversation_logs"
    audio_dir: Path = base_dir / "data" / "audio_out"
    audio_in_dir: Path = base_dir / "data" / "audio_in"
