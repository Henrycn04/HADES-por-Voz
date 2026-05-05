import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    base_dir: Path = Path(__file__).resolve().parents[1]

    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")

    text_model: str = os.getenv("HADES_TEXT_MODEL", "gemini-2.5-flash")
    tts_model: str = os.getenv("HADES_TTS_MODEL", "gemini-3.1-flash-tts-preview")
    tts_voice: str = os.getenv("HADES_TTS_VOICE", "Kore")

    enable_tts: bool = os.getenv("HADES_ENABLE_TTS", "true").lower() == "true"
    autoplay_tts: bool = os.getenv("HADES_AUTOPLAY_TTS", "true").lower() == "true"

    memory_path: Path = base_dir / "memory" / "user_memory.json"
    logs_dir: Path = base_dir / "data" / "conversation_logs"
    audio_dir: Path = base_dir / "data" / "audio_out"
