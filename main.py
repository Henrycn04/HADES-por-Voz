from config.settings import Settings
from agent.gemini_client import GeminiTextClient
from agent.conversation_agent import ConversationAgent
from memory.memory_manager import MemoryManager
from pattern_extraction.pattern_extractor import PatternExtractor
from interpretation.context_interpreter import ContextInterpreter
from voice.tts import GeminiTTS


def print_header():
    print("\n" + "=" * 64)
    print("HADES por Voz")
    print("=" * 64)


def main():
    settings = Settings()

    if not settings.gemini_api_key:
        print("No se encontró GEMINI_API_KEY en .env")


    gemini = GeminiTextClient(settings)
    memory_manager = MemoryManager(settings)
    extractor = PatternExtractor(gemini)
    interpreter = ContextInterpreter(gemini)
    tts = GeminiTTS(settings)

    conversation_agent = ConversationAgent(
        memory_manager=memory_manager,
        extractor=extractor,
        tts=tts,
        logs_dir=settings.logs_dir,
    )

    while True:
        print_header()
        print("1. Conversación inicial para aprender patrones")
        print("2. Probar una situación actual")
        print("3. Ver memoria JSON")
        print("4. Probar TTS")
        print("5. Salir")

        option = input("\nOpción: ").strip()

        if option == "1":
            conversation_agent.run_initial_conversation()

        elif option == "2":
            current_context = input(
                "\nDescriba la situación actual. Ejemplo: "
                "Son las 9:40 PM, llegué tarde, tomé café y mañana tengo agenda libre.\n\nSituación: "
            ).strip()

            memory = memory_manager.load_memory()
            result = interpreter.interpret(memory, current_context)

            print("\n--- Interpretación de HADES ---")
            print(f"Desviación detectada: {result.get('deviation_detected')}")
            print(f"Razón: {result.get('deviation_reason')}")
            print("\nHipótesis:")
            for h in result.get("hypotheses", []):
                print(f"- ({h.get('confidence')}) {h.get('hypothesis')}")

            response = result.get("agent_response", "No pude generar una respuesta final.")
            print(f"\nHADES: {response}")
            tts.speak(response, filename="hades_context_response.wav")

        elif option == "3":
            print("\n--- Memoria actual ---")
            print(memory_manager.pretty_memory())

        elif option == "4":
            text = input("\nTexto para que HADES lo diga: ").strip()
            print(f"\nHADES: {text}")
            tts.speak(text, filename="hades_tts_test.wav")

        elif option == "5":
            print("\nCerrando HADES")
            break

        else:
            print("\nOpción inválida.")


if __name__ == "__main__":
    main()
