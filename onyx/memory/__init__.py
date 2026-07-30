from onyx.memory.interfaces import MemoryConfig, MemoryItem, MemoryQuery, MemoryResult, MemoryScope
from onyx.memory.manager import MemoryManager


class Memory:

    def __init__(self, config: MemoryConfig | None = None):
        self._manager = MemoryManager(config)
        self.short_term = self._manager.short_term
        self.long_term = self._manager.long_term
        self.episodic = self._manager.episodic
        self.semantic = self._manager.semantic

    def search(self, query: str | MemoryQuery, limit: int = 10) -> MemoryResult:
        if isinstance(query, str):
            query = MemoryQuery(text=query, limit=limit)
        return self._manager.search(query)

    def remember(self, category: str, key: str, value: str, ttl_days: int | None = None) -> bool:
        return self._manager.remember(category, key, value, ttl_days)

    def recall(self, category: str, key: str, default: str | None = None) -> str | None:
        return self._manager.recall(category, key, default)

    def add_turn(self, role: str, content: str):
        self._manager.add_turn(role, content)

    def record_episode(self, **kwargs) -> int | None:
        return self._manager.record_episode(**kwargs)

    def format_for_prompt(self, query: str = "", max_chars: int = 5000) -> str:
        return self._manager.format_for_prompt(query=query, max_chars=max_chars)

    @property
    def stats(self) -> dict:
        return {
            "short_term": self.short_term.stats,
            "semantic": self.semantic.stats,
        }
