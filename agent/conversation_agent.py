from datetime import datetime
from pathlib import Path

from memory.memory_manager import MemoryManager
from pattern_extraction.pattern_extractor import PatternExtractor
from voice.tts import GeminiTTS


class ConversationAgent:
    def __init__(
        self,
        memory_manager: MemoryManager,
        extractor: PatternExtractor,
        tts: GeminiTTS,
        logs_dir: Path,
    ):
        self.memory_manager = memory_manager
        self.extractor = extractor
        self.tts = tts
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def run_initial_conversation(self) -> dict:
        questions = [
            "Hola, soy HADES. Quiero conocerle un poco para entender mejor tus rutinas. ¿Cómo suele ser un día normal para usted?",
            "¿Qué cosas hace casi siempre a la misma hora o en el mismo orden?",
            "¿Qué cosas suelen cambiar esa rutina? Por ejemplo cansancio, café, estrés, estudio, trabajo o planes.",
            "Cuando rompe una rutina, ¿normalmente qué significa? ¿Que querés descansar, seguir trabajando, distraerte, evitar algo o resolver algo pendiente?",
            "¿Qué te gustaría que un asistente doméstico entienda de usted sin tener que explicárselo cada vez?"
        ]

        transcript_lines: list[str] = []

        for question in questions:
            print(f"\nHADES: {question}")
            self.tts.speak(question)
            answer = input("Usuario: ").strip()
            transcript_lines.append(f"HADES: {question}")
            transcript_lines.append(f"Usuario: {answer}")

        transcript = "\n".join(transcript_lines)
        self._save_transcript(transcript)

        print("\nHADES: Voy a convertir esta conversación en memoria contextual.")
        extraction = self.extractor.extract(transcript)
        memory = self.memory_manager.merge_extracted_patterns(extraction)

        summary = extraction.get("profile_summary", "Memoria actualizada.")
        final_msg = f"Listo. Aprendí esto como base: {summary}"
        print(f"\nHADES: {final_msg}")
        self.tts.speak(final_msg, filename="hades_memory_summary.wav")

        return memory

    def _save_transcript(self, transcript: str) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.logs_dir / f"conversation_{stamp}.txt"
        path.write_text(transcript, encoding="utf-8")
