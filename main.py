from config.settings import Settings
from agent.llm_factory import create_text_client
from agent.hades_assistant import HadesAssistant
from memory.memory_manager import MemoryManager
from pattern_extraction.pattern_extractor import PatternExtractor


def print_header():
    print("\n" + "=" * 64)
    print("HADES por Voz")
    print("=" * 64)


def create_profile(memory_manager: MemoryManager) -> None:
    profile_name = input("\nNombre de la persona: ").strip()
    if not profile_name:
        print("No se creó ningún perfil.")
        return

    memory_manager.set_profile(profile_name)
    print(f"Perfil creado/cargado: {memory_manager.get_active_profile_name()}")


def show_profiles(memory_manager: MemoryManager) -> list[str]:
    profiles = memory_manager.list_profiles()
    if not profiles:
        print("\nTodavía no hay perfiles guardados.")
        return []

    print("\nPerfiles existentes:")
    for idx, profile in enumerate(profiles, start=1):
        print(f"{idx}. {profile}")
    return profiles


def run_hades_mode(settings: Settings, llm, memory_manager: MemoryManager, extractor: PatternExtractor) -> None:
    assistant = HadesAssistant(
        settings=settings,
        llm=llm,
        memory_manager=memory_manager,
        extractor=extractor,
    )
    assistant.run_until_menu()


def main():
    settings = Settings()
    memory_manager = MemoryManager(settings)

    print("\nInicializando LLM...")
    llm = create_text_client(settings)
    extractor = PatternExtractor(llm)

    while True:
        print_header()
        print("1. Modo HADES")
        print("2. Crear perfil")
        print("3. Usar perfil")
        print("4. Ver perfiles")
        print("5. Salir")

        option = input("\nOpción: ").strip()

        if option == "1":
            memory_manager.set_profile("General")
            print("\nEntrando a Modo HADES con perfil General.")
            run_hades_mode(settings, llm, memory_manager, extractor)

        elif option == "2":
            create_profile(memory_manager)

        elif option == "3":
            profiles = show_profiles(memory_manager)
            if not profiles:
                continue

            choice = input("\nElegí el número del perfil, o 0 para volver: ").strip()
            if choice == "0":
                continue

            try:
                index = int(choice) - 1
                selected = profiles[index]
            except (ValueError, IndexError):
                print("Opción inválida.")
                continue

            memory_manager.set_profile(selected)
            print(f"\nEntrando a Modo HADES con perfil: {selected}")
            run_hades_mode(settings, llm, memory_manager, extractor)

        elif option == "4":
            show_profiles(memory_manager)

        elif option == "5":
            print("\nCerrando HADES. Memoria guardada.")
            break

        else:
            print("Opción inválida.")


if __name__ == "__main__":
    main()
