from onyx.memory.interfaces import MemoryConfig, MemoryItem, MemoryScope


class LongTermMemory:

    def __init__(self, config: MemoryConfig | None = None):
        cfg = config or MemoryConfig()
        self._max_chars = cfg.long_term_max_chars
        self._max_per_category = cfg.long_term_max_entries_per_category

    def remember(self, category: str, key: str, value: str, ttl_days: int | None = None) -> bool:
        from memory.memory_manager import update_memory
        try:
            update_memory({category: {key: {"value": value}}}, ttl_days=ttl_days)
            return True
        except Exception:
            return False

    def recall(self, category: str, key: str, default: str | None = None) -> str | None:
        from memory.memory_manager import recall as _recall
        try:
            return _recall(category, key, default)
        except Exception:
            return default

    def search(self, query: str, category: str = "", limit: int = 10) -> list[MemoryItem]:
        from memory.memory_manager import categories as _categories, recall as _recall
        items: list[MemoryItem] = []
        q = query.lower()
        cats = [category] if category else _categories()
        for cat in cats:
            from memory.memory_manager import category_keys as _keys
            for key in _keys(cat):
                val = _recall(cat, key)
                if val and q in val.lower():
                    items.append(MemoryItem(
                        content=val,
                        category=cat,
                        key=key,
                        scope=MemoryScope.LONG_TERM,
                    ))
                    if len(items) >= limit:
                        break
            if len(items) >= limit:
                break
        return items

    def forget(self, category: str, key: str) -> bool:
        from memory.memory_manager import forget
        try:
            return forget(category, key)
        except Exception:
            return False

    def list_categories(self) -> list[str]:
        from memory.memory_manager import categories
        try:
            return categories()
        except Exception:
            return []

    def category_keys(self, category: str) -> list[str]:
        from memory.memory_manager import category_keys
        try:
            return category_keys(category)
        except Exception:
            return []

    def format_for_prompt(self) -> str:
        from memory.memory_manager import load_memory, format_memory_for_prompt
        try:
            memory = load_memory()
            return format_memory_for_prompt(memory)
        except Exception:
            return ""
