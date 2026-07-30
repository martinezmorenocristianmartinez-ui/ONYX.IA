from onyx.memory.interfaces import MemoryConfig, MemoryItem, MemoryQuery, MemoryResult
from onyx.memory.short_term import ShortTermMemory
from onyx.memory.long_term import LongTermMemory
from onyx.memory.episodic import EpisodicMemory
from onyx.memory.semantic import SemanticMemory


class MemoryManager:

    def __init__(self, config: MemoryConfig | None = None):
        self.config = config or MemoryConfig()
        self.short_term = ShortTermMemory(self.config)
        self.long_term = LongTermMemory(self.config)
        self.episodic = EpisodicMemory(self.config)
        self.semantic = SemanticMemory(self.config)

    def search(self, query: MemoryQuery) -> MemoryResult:
        all_items: list[MemoryItem] = []
        scopes = query.scopes or [s for s in _ALL_SCOPES]
        limit_per = query.limit

        if _SCOPE_LONG in scopes:
            all_items.extend(self.long_term.search(query.text, query.category, limit_per))
        if _SCOPE_EPISODIC in scopes:
            all_items.extend(self.episodic.search(query.text, limit_per))
        if _SCOPE_SEMANTIC in scopes:
            all_items.extend(self.semantic.search(query.text, limit_per))
        if _SCOPE_SHORT in scopes:
            recent = self.short_term.format_for_prompt(max_recent=limit_per)
            if recent:
                all_items.append(MemoryItem(
                    content=recent,
                    category="conversation",
                    scope=MemoryScope.SHORT_TERM,
                ))

        all_items.sort(key=lambda x: x.score, reverse=True)
        return MemoryResult(items=all_items[:query.limit], total=len(all_items), query=query.text)

    def format_for_prompt(self, query: str = "", max_chars: int = 5000) -> str:
        parts = []
        lt = self.long_term.format_for_prompt()
        if lt:
            parts.append(f"[MEMORIA DE LARGO PLAZO]\n{lt}")
        epi = self.episodic.format_for_prompt(query=query)
        if epi:
            parts.append(f"[EPISODIOS RELEVANTES]\n{epi}")
        vec = self.semantic.format_for_prompt(query=query)
        if vec:
            parts.append(f"[MEMORIA SEMANTICA]\n{vec}")
        st = self.short_term.format_for_prompt()
        if st:
            parts.append(f"[CONVERSACION RECIENTE]\n{st}")
        return "\n\n".join(parts) if parts else ""

    def remember(self, category: str, key: str, value: str, ttl_days: int | None = None) -> bool:
        return self.long_term.remember(category, key, value, ttl_days)

    def recall(self, category: str, key: str, default: str | None = None) -> str | None:
        return self.long_term.recall(category, key, default)

    def add_turn(self, role: str, content: str):
        self.short_term.add_turn(role, content)

    def record_episode(
        self,
        user_message: str = "",
        onyx_response: str = "",
        tool_calls: list | None = None,
        tool_results: list | None = None,
        success_score: int = 5,
        tags: str = "",
    ):
        return self.episodic.record(
            user_message=user_message,
            onyx_response=onyx_response,
            tool_calls=tool_calls,
            tool_results=tool_results,
            success_score=success_score,
            tags=tags,
        )


from onyx.memory.interfaces import MemoryScope
_SCOPE_SHORT = MemoryScope.SHORT_TERM
_SCOPE_LONG = MemoryScope.LONG_TERM
_SCOPE_EPISODIC = MemoryScope.EPISODIC
_SCOPE_SEMANTIC = MemoryScope.SEMANTIC
_ALL_SCOPES = [_SCOPE_SHORT, _SCOPE_LONG, _SCOPE_EPISODIC, _SCOPE_SEMANTIC]
