from config.settings import Settings
from memory.memory_manager import MemoryManager


def test_memory_loads():
    settings = Settings()
    manager = MemoryManager(settings)
    memory = manager.load_memory()
    assert "user_profile" in memory
