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
        
    def _save_transcript(self, transcript: str) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        profile = self.memory_manager.get_active_profile_name()
        path = self.logs_dir / f"conversation_{profile}_{stamp}.txt"
        path.write_text(transcript, encoding="utf-8")

    def run_initial_conversation(self) -> dict:
        if not self.memory_manager.has_active_profile():
            profile_name = input(
                "\nHADES: Primero, ¿con qué nombre quiere guardar este perfil?\nUsuario: "
            ).strip()

            self.memory_manager.set_profile(profile_name)

            greeting = (
                f"Perfecto, voy a guardar esta memoria como perfil de "
                f"{self.memory_manager.get_active_profile_name()}."
            )

            print(f"\nHADES: {greeting}")
            self.tts.speak(greeting, filename="hades_profile_created.wav")

            transcript_lines: list[str] = [
                "HADES: Primero, ¿con qué nombre quiere guardar este perfil?",
                f"Usuario: {self.memory_manager.get_active_profile_name()}",
                f"HADES: {greeting}"
            ]

        else:
            greeting = (
                f"Perfecto, voy a continuar usando el perfil de "
                f"{self.memory_manager.get_active_profile_name()}."
            )

            print(f"\nHADES: {greeting}")
            self.tts.speak(greeting, filename="hades_profile_active.wav")

            transcript_lines: list[str] = [
                f"HADES: {greeting}"
            ]

        questions = [
            "Hola, soy HADES. Quiero conocerle un poco para entender mejor sus rutinas. ¿Cómo suele ser un día normal para usted?",
            "¿Qué cosas hace casi siempre a la misma hora o en el mismo orden?",
            "¿Qué cosas suelen cambiar esa rutina? Por ejemplo cansancio, café, estrés, estudio, trabajo o planes.",
            "Cuando rompe una rutina, ¿normalmente qué significa? ¿Que quiere descansar, seguir trabajando, distraerse, evitar algo o resolver algo pendiente?",
            "¿Qué le gustaría que un asistente doméstico entienda de usted sin tener que explicárselo cada vez?"
        ]

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
