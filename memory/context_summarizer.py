"""
context_summarizer.py — Compresses conversation history locally to stay within
context limits. Uses extractive summarization (TF-IDF sentence scoring) for
zero-dependency operation. Injects compressed history into system prompt.
"""
import re
import threading
from collections import Counter, deque
from datetime import datetime
from typing import Optional


class ContextSummarizer:
    """Tracks conversation turns, compresses old ones into compact summaries."""

    def __init__(self, max_active_turns: int = 25, max_stored_summaries: int = 20):
        self.buffer: deque[dict] = deque(maxlen=max_active_turns + 10)
        self.summaries: deque[str] = deque(maxlen=max_stored_summaries)
        self.max_active = max_active_turns
        self._turn_count = 0

    def add_turn(self, role: str, content: str) -> None:
        """Record a conversation turn (user or assistant)."""
        if not content or not content.strip():
            return
        self._turn_count += 1
        self.buffer.append({
            "role": role,
            "content": content[:1200],
            "ts": datetime.now().isoformat(),
            "turn": self._turn_count,
        })
        self._maybe_compress()

    def _maybe_compress(self) -> None:
        while len(self.buffer) >= self.max_active:
            chunk = [self.buffer.popleft() for _ in range(min(5, len(self.buffer)))]
            summary = self._extractive_summarize(chunk)
            if summary:
                self.summaries.append(summary)

    def _extractive_summarize(self, turns: list[dict]) -> Optional[str]:
        texts = [t["content"] for t in turns if t["content"]]
        if not texts:
            return None

        full = " ".join(texts)
        sentences = re.split(r"(?<=[.!?])\s+", full)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

        if len(sentences) <= 2:
            return full[:400]

        words = re.findall(r"\w+", full.lower())
        stopwords = {
            "el","la","los","las","de","del","en","un","una","que","y","a",
            "es","por","con","para","se","no","lo","su","al","le","este",
            "esta","esto","como","más","pero","sus","son","era","han","ha",
            "fue","eso","esa","ese","les","dos","muy","sin","sobre","entre",
            "tiene","tenia","habia","todo","tambien","aqui","donde","cuando",
            "despues","entonces","asi","aunque","porque","solo","tanto",
        }
        freq = Counter(w for w in words if w not in stopwords and len(w) > 2)

        scored = []
        for s in sentences:
            s_words = re.findall(r"\w+", s)
            s_lower = [w.lower() for w in s_words]
            score = sum(freq.get(w, 0) for w in s_lower)
            scored.append((score, s))

        scored.sort(key=lambda x: -x[0])
        keep = max(1, int(len(scored) * 0.35))
        selected = [s for _, s in scored[:keep]]

        summary = " | ".join(selected)
        # Trim to reasonable length
        while len(summary) > 600:
            if selected:
                selected.pop()
                summary = " | ".join(selected)
            else:
                break
        return summary if summary else None

    def format_for_prompt(self, max_summaries: int = 8, max_recent: int = 10) -> str:
        """Build compressed history block for system prompt injection."""
        if not self.summaries and not self.buffer:
            return ""

        parts = []
        summaries_list = list(self.summaries)
        buffer_list = list(self.buffer)

        if summaries_list:
            parts.append("[HISTORIAL COMPRIMIDO - turnos anteriores]")
            for i, s in enumerate(summaries_list[-max_summaries:], 1):
                parts.append(f"  Bloque {i}: {s}")

        if buffer_list:
            parts.append("[TURNOS RECIENTES]")
            for t in buffer_list[-max_recent:]:
                prefix = "Usuario" if t["role"] == "user" else "ONYX"
                parts.append(f"  {prefix}: {t['content'][:400]}")

        return "\n".join(parts)

    def get_summary_stats(self) -> str:
        return (
            f"Summarizer: {len(self.summaries)} compressed blocks, "
            f"{len(self.buffer)} recent turns, {self._turn_count} total turns"
        )


_summarizer: Optional[ContextSummarizer] = None
_summarizer_lock = threading.Lock()


def get_summarizer() -> ContextSummarizer:
    global _summarizer
    with _summarizer_lock:
        if _summarizer is None:
            _summarizer = ContextSummarizer()
        return _summarizer
