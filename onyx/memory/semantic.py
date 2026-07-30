from onyx.memory.interfaces import MemoryConfig, MemoryItem, MemoryScope


class SemanticMemory:

    def __init__(self, config: MemoryConfig | None = None):
        cfg = config or MemoryConfig()
        self._max_entries = cfg.semantic_max_entries
        self._similarity_threshold = cfg.semantic_similarity_threshold

    def add(self, text: str, metadata: dict | None = None) -> bool:
        from memory.vector_memory import get_vector_memory
        try:
            mem = get_vector_memory()
            mem.add(text, metadata or {})
            return True
        except Exception:
            return False

    def search(self, query: str, limit: int = 10) -> list[MemoryItem]:
        from memory.vector_memory import get_vector_memory
        try:
            mem = get_vector_memory()
            results = mem.search(query, top_k=limit)
            return [
                MemoryItem(
                    content=r[0].get("summary", ""),
                    category=r[0].get("tool", "semantic"),
                    scope=MemoryScope.SEMANTIC,
                    timestamp=r[0].get("timestamp", 0.0),
                    score=r[1],
                    metadata=r[0],
                )
                for r in results
            ]
        except Exception:
            return []

    def format_for_prompt(self, query: str = "", max_chars: int = 4000) -> str:
        from memory.vector_memory import get_vector_memory
        try:
            mem = get_vector_memory()
            return mem.format_for_prompt(query, max_chars=max_chars)
        except Exception:
            return ""

    @property
    def stats(self) -> dict:
        from memory.vector_memory import get_vector_memory
        try:
            mem = get_vector_memory()
            return mem.stats()
        except Exception:
            return {"total": 0}
