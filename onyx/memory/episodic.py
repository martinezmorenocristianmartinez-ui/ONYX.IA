from onyx.memory.interfaces import MemoryConfig, MemoryItem, MemoryScope


class EpisodicMemory:

    def __init__(self, config: MemoryConfig | None = None):
        cfg = config or MemoryConfig()
        self._max_episodes = cfg.episodic_max_episodes

    def record(
        self,
        user_message: str = "",
        onyx_response: str = "",
        tool_calls: list | None = None,
        tool_results: list | None = None,
        success_score: int = 5,
        summary: str = "",
        tags: str = "",
    ) -> int | None:
        from memory.episodic_memory import get_memory
        try:
            mem = get_memory()
            episode_id = mem.record(
                user_message=user_message,
                onyx_response=onyx_response,
                tool_calls=tool_calls,
                tool_results=tool_results,
                success_score=success_score,
                summary=summary,
                tags=tags,
            )
            return episode_id
        except Exception:
            return None

    def search(self, query: str, limit: int = 10) -> list[MemoryItem]:
        from memory.episodic_memory import get_memory
        try:
            mem = get_memory()
            results = mem.retrieve(query, max_results=limit)
            return [
                MemoryItem(
                    content=r.get("summary", r.get("onyx_response", "")),
                    category="episodic",
                    scope=MemoryScope.EPISODIC,
                    timestamp=r.get("timestamp", 0.0),
                    score=r.get("success_score", 5),
                    metadata=r,
                )
                for r in results
            ]
        except Exception:
            return []

    def recent(self, count: int = 10) -> list[MemoryItem]:
        from memory.episodic_memory import get_memory
        try:
            mem = get_memory()
            results = mem.retrieve_recent(count=count)
            return [
                MemoryItem(
                    content=r.get("summary", r.get("onyx_response", "")),
                    category="episodic",
                    scope=MemoryScope.EPISODIC,
                    timestamp=r.get("timestamp", 0.0),
                    score=r.get("success_score", 5),
                    metadata=r,
                )
                for r in results
            ]
        except Exception:
            return []

    def format_for_prompt(self, query: str = "", recent_count: int = 3) -> str:
        from memory.episodic_memory import get_memory
        try:
            mem = get_memory()
            return mem.format_for_prompt(query=query, recent_count=recent_count)
        except Exception:
            return ""
