from dataclasses import dataclass, field


@dataclass
class BrainResult:
    text: str = ""
    speak: bool = False
    state: str = ""
    actions: list[dict] = field(default_factory=list)
    from_cache: bool = False
