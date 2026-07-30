from collections import deque
from datetime import datetime

from onyx.memory.interfaces import MemoryConfig


_TURN_SEPARATOR = " | "


class ShortTermMemory:

    def __init__(self, config: MemoryConfig | None = None):
        cfg = config or MemoryConfig()
        self._capacity = cfg.short_term_capacity
        self._compress_threshold = cfg.short_term_compress_threshold
        self._buffer: deque[dict] = deque(maxlen=self._capacity)
        self._summaries: deque[str] = deque(maxlen=20)
        self._turn_count = 0

    def add_turn(self, role: str, content: str):
        self._turn_count += 1
        truncated = content[:1200] if len(content) > 1200 else content
        self._buffer.append({
            "role": role,
            "content": truncated,
            "timestamp": datetime.now().isoformat(),
            "turn": self._turn_count,
        })
        self._maybe_compress()

    def _maybe_compress(self):
        if len(self._buffer) < self._compress_threshold:
            return
        to_compress = [self._buffer.popleft() for _ in range(5)]
        text = " ".join(t["content"] for t in to_compress)
        summary = self._extractive_summarize(text)
        if summary:
            self._summaries.append(summary)

    def _extractive_summarize(self, text: str) -> str:
        import re
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        if len(sentences) <= 2:
            return text[:600]
        words = re.findall(r"\w+", text.lower())
        stopwords = {
            "de", "la", "que", "el", "en", "y", "a", "los", "del", "se",
            "las", "por", "un", "para", "con", "no", "una", "su", "al",
            "es", "lo", "como", "más", "pero", "sus", "le", "ya", "este",
            "entre", "porque", "ese", "esta", "desde", "todo", "ella",
            "sin", "cuando", "también", "fue", "muy", "era", "solo",
            "está", "tiene", "ser", "había", "dijo", "cada", "qué",
            "hasta", "donde", "quien", "así", "todos", "ello", "tras",
        }
        freq = {}
        for w in words:
            if w not in stopwords and len(w) > 2:
                freq[w] = freq.get(w, 0) + 1
        max_freq = max(freq.values()) if freq else 1
        scored = []
        for s in sentences:
            if len(s.split()) < 3:
                continue
            s_words = re.findall(r"\w+", s.lower())
            score = sum(freq.get(w, 0) / max_freq for w in s_words if w in freq)
            scored.append((score / max(len(s_words), 1), s))
        scored.sort(key=lambda x: x[0], reverse=True)
        keep = max(1, int(len(scored) * 0.35))
        result = _TURN_SEPARATOR.join(s[1] for s in scored[:keep])
        return result[:600]

    def format_for_prompt(self, max_summaries: int = 8, max_recent: int = 10) -> str:
        parts = []
        summaries_list = list(self._summaries)
        if summaries_list:
            summary_block = "\n".join(summaries_list[-max_summaries:])
            parts.append(f"[RESUMEN DE CONVERSACION ANTERIOR]\n{summary_block}")
        recent = list(self._buffer)[-max_recent:]
        if recent:
            recent_lines = [
                f"{t['role']}: {t['content']}" for t in recent
            ]
            parts.append(f"[TURNOS RECIENTES]\n" + "\n".join(recent_lines))
        return "\n\n".join(parts) if parts else ""

    def clear(self):
        self._buffer.clear()
        self._summaries.clear()
        self._turn_count = 0

    @property
    def stats(self) -> dict:
        return {
            "buffer": len(self._buffer),
            "summaries": len(self._summaries),
            "turns": self._turn_count,
        }
