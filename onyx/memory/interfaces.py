from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MemoryScope(Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


@dataclass
class MemoryItem:
    content: str
    category: str = ""
    key: str = ""
    scope: MemoryScope = MemoryScope.LONG_TERM
    timestamp: float = 0.0
    score: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class MemoryQuery:
    text: str = ""
    category: str = ""
    scopes: list[MemoryScope] | None = None
    limit: int = 10
    min_score: float = 0.0


@dataclass
class MemoryResult:
    items: list[MemoryItem] = field(default_factory=list)
    total: int = 0
    from_cache: bool = False
    query: str = ""


@dataclass
class MemoryConfig:
    short_term_capacity: int = 35
    short_term_compress_threshold: int = 25
    long_term_max_chars: int = 25000
    long_term_max_entries_per_category: int = 500
    long_term_default_ttl_days: int = 90
    semantic_max_entries: int = 8000
    semantic_similarity_threshold: float = 0.22
    episodic_max_episodes: int = 25000
