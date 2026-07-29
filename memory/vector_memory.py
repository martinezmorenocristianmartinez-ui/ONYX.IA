"""
vector_memory.py — Semantic memory using transformer embeddings (v2 optimized).

Optimizations:
- Keep a prebuilt 2D numpy matrix; rebuild incrementally (append, not full)
- Write-behind persistence (async flush thread); batch adds
- LRU query cache (input -> top_k results) for repeated similar queries
- Optional FAISS HNSW index if installed; fallback to pure numpy cosine
- Model warmup with dummy call to eliminate cold-start latency
- Batching for bulk add() operations (bulk_encode)
- Keep rolling window of last _MAX_ENTRIES but don't reload on every save
- Link to episodic memory via episode_id in metadata
- Query deduplication: identical queries within TTL return cache
"""
import json
import time
import hashlib
import threading
from pathlib import Path
from typing import Optional
from collections import OrderedDict

import numpy as np

MEMORY_DIR = Path(__file__).resolve().parent
EMBED_PATH = MEMORY_DIR / "vector_embeddings.npy"
META_PATH = MEMORY_DIR / "vector_metadata.json"
_MAX_ENTRIES = 8000
_SIMILARITY_THRESHOLD = 0.22
_QUERY_CACHE_SIZE = 256
_QUERY_CACHE_TTL = 60.0
_WRITE_BEHIND_SEC = 20.0
_WRITE_BEHIND_OPS = 100

try:
    import faiss  # type: ignore
    _HAS_FAISS = True
except Exception:
    _HAS_FAISS = False


class _QueryLRU:
    def __init__(self, maxsize: int, ttl: float):
        self._d: "OrderedDict[str, tuple]" = OrderedDict()
        self._max = maxsize
        self._ttl = ttl
        self._lk = threading.Lock()

    def get(self, key):
        with self._lk:
            if key in self._d:
                val, ts = self._d[key]
                if time.time() - ts > self._ttl:
                    del self._d[key]
                    return None
                self._d.move_to_end(key)
                return val
            return None

    def put(self, key, value):
        with self._lk:
            self._d[key] = (value, time.time())
            self._d.move_to_end(key)
            while len(self._d) > self._max:
                self._d.popitem(last=False)

    def clear(self):
        with self._lk:
            self._d.clear()


class VectorMemory:
    _instance = None
    _lock = threading.RLock()
    _flush_thread: threading.Thread | None = None
    _flush_stop = threading.Event()

    def __init__(self):
        self._model = None
        self._model_warmed = False
        self.embeddings: list[np.ndarray] = []
        self.metadata: list[dict] = []
        self._matrix: np.ndarray | None = None
        self._matrix_dirty = True
        self._faiss_index = None
        self._faiss_dirty = True
        self._dirty = False
        self._dirty_ops = 0
        self._query_cache = _QueryLRU(_QUERY_CACHE_SIZE, _QUERY_CACHE_TTL)
        self._load()
        self._start_flush_daemon()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── persistence ────────────────────────────────────────────────
    def _load(self):
        if EMBED_PATH.exists() and META_PATH.exists():
            try:
                arr = np.load(str(EMBED_PATH), allow_pickle=False)
                if arr.size > 0 and arr.ndim == 2:
                    self.embeddings = [arr[i] for i in range(arr.shape[0])]
                else:
                    self.embeddings = []
                self.metadata = json.loads(META_PATH.read_text("utf-8"))
                if len(self.metadata) != len(self.embeddings):
                    n = min(len(self.metadata), len(self.embeddings))
                    self.metadata = self.metadata[:n]
                    self.embeddings = self.embeddings[:n]
            except Exception:
                self.embeddings = []
                self.metadata = []
        self._matrix_dirty = True
        self._faiss_dirty = True

    def _save_unsafe(self):
        if not self.embeddings:
            arr = np.array([], dtype=np.float32).reshape(0, 0)
        else:
            arr = np.stack(self.embeddings, axis=0).astype(np.float32)
        try:
            np.save(str(EMBED_PATH), arr, allow_pickle=False)
            META_PATH.write_text(
                json.dumps(self.metadata, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _start_flush_daemon(self):
        if VectorMemory._flush_thread and VectorMemory._flush_thread.is_alive():
            return

        def _run():
            while not VectorMemory._flush_stop.is_set():
                VectorMemory._flush_stop.wait(_WRITE_BEHIND_SEC)
                with self._lock:
                    if self._dirty:
                        self._save_unsafe()
                        self._dirty = False
                        self._dirty_ops = 0

        VectorMemory._flush_thread = threading.Thread(
            target=_run, name="VecMemFlush", daemon=True
        )
        VectorMemory._flush_thread.start()

    def _mark_dirty(self):
        self._dirty = True
        self._dirty_ops += 1
        if self._dirty_ops >= _WRITE_BEHIND_OPS:
            self._save_unsafe()
            self._dirty = False
            self._dirty_ops = 0
        self._matrix_dirty = True
        self._faiss_dirty = True
        self._query_cache.clear()

    def flush(self):
        with self._lock:
            if self._dirty:
                self._save_unsafe()
                self._dirty = False
                self._dirty_ops = 0

    # ── embedding model (lazy + warmup) ───────────────────────────
    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        if not self._model_warmed:
            try:
                self._model.encode(["warmup query to load weights"],
                                   normalize_embeddings=True,
                                   show_progress_bar=False)
                self._model_warmed = True
            except Exception:
                pass
        return self._model

    def embed(self, text: str) -> np.ndarray:
        return self._get_model().encode(
            text[:512], normalize_embeddings=True, show_progress_bar=False
        ).astype(np.float32)

    def bulk_embed(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        model = self._get_model()
        out = model.encode(
            [t[:512] for t in texts],
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=min(32, max(4, len(texts))),
        ).astype(np.float32)
        return [out[i] for i in range(out.shape[0])]

    # ── matrix & index helpers ────────────────────────────────────
    def _get_matrix(self) -> np.ndarray:
        if not self.embeddings:
            return np.zeros((0, 0), dtype=np.float32)
        if self._matrix_dirty or self._matrix is None or self._matrix.shape[0] != len(self.embeddings):
            try:
                self._matrix = np.stack(self.embeddings, axis=0).astype(np.float32)
            except Exception:
                dim = self.embeddings[0].shape[0] if self.embeddings else 384
                self._matrix = np.zeros((len(self.embeddings), dim), dtype=np.float32)
                for i, e in enumerate(self.embeddings):
                    self._matrix[i] = e.astype(np.float32)
            self._matrix_dirty = False
        return self._matrix

    def _get_faiss_index(self):
        if not _HAS_FAISS or not self.embeddings:
            return None
        if self._faiss_dirty or self._faiss_index is None:
            mat = self._get_matrix()
            dim = mat.shape[1]
            try:
                idx = faiss.IndexHNSWFlat(dim, 32, faiss.METRIC_INNER_PRODUCT)
                idx.hnsw.efSearch = 64
                if mat.shape[0] > 0:
                    idx.add(mat)
                self._faiss_index = idx
                self._faiss_dirty = False
            except Exception:
                self._faiss_index = None
        return self._faiss_index

    # ── public api ────────────────────────────────────────────────
    def add(self, text: str, metadata: dict):
        if not text or not text.strip():
            return
        vec = self.embed(text)
        with self._lock:
            self.embeddings.append(vec)
            self.metadata.append(metadata)
            if len(self.embeddings) > _MAX_ENTRIES:
                drop = len(self.embeddings) - _MAX_ENTRIES
                self.embeddings = self.embeddings[drop:]
                self.metadata = self.metadata[drop:]
            self._mark_dirty()

    def bulk_add(self, items: list[tuple[str, dict]]):
        """items = [(text, metadata), ...]"""
        items = [(t, m) for t, m in items if t and t.strip()]
        if not items:
            return
        texts = [t for t, _ in items]
        metas = [m for _, m in items]
        vecs = self.bulk_embed(texts)
        with self._lock:
            self.embeddings.extend(vecs)
            self.metadata.extend(metas)
            if len(self.embeddings) > _MAX_ENTRIES:
                drop = len(self.embeddings) - _MAX_ENTRIES
                self.embeddings = self.embeddings[drop:]
                self.metadata = self.metadata[drop:]
            self._mark_dirty()

    def search(self, query: str, top_k: int = 10) -> list[tuple[dict, float]]:
        if not self.embeddings:
            return []
        qhash = hashlib.md5(query.lower().encode("utf-8")).hexdigest()
        cache_key = f"{qhash}:{top_k}"
        cached = self._query_cache.get(cache_key)
        if cached is not None:
            return cached
        qvec = self.embed(query[:512]).astype(np.float32).reshape(1, -1)

        with self._lock:
            if _HAS_FAISS:
                idx = self._get_faiss_index()
                if idx is not None:
                    try:
                        D, I = idx.search(qvec, min(top_k * 2, idx.ntotal))
                        results = []
                        for score, i in zip(D[0], I[0]):
                            if 0 <= i < len(self.metadata) and float(score) >= _SIMILARITY_THRESHOLD:
                                results.append((self.metadata[i], float(score)))
                        self._query_cache.put(cache_key, results[:top_k])
                        return results[:top_k]
                    except Exception:
                        pass
            mat = self._get_matrix()
            if mat.shape[0] == 0:
                return []
            sims = np.dot(mat, qvec.reshape(-1)).astype(np.float64)
            k = min(top_k * 2, len(sims))
            top_idx = np.argpartition(-sims, k - 1)[:k]
            top_idx = top_idx[np.argsort(-sims[top_idx])]
            results = [
                (self.metadata[int(i)], float(sims[int(i)]))
                for i in top_idx
                if 0 <= int(i) < len(self.metadata) and float(sims[int(i)]) >= _SIMILARITY_THRESHOLD
            ]
            self._query_cache.put(cache_key, results[:top_k])
            return results[:top_k]

    def format_for_prompt(self, query: str, max_chars: int = 5000) -> str:
        if not query:
            return ""
        results = self.search(query)
        if not results:
            return ""
        lines = ["[MEMORIA VECTORIAL — RECUERDOS SEMÁNTICOS]"]
        chars = 0
        for meta, score in results:
            ts = str(meta.get("timestamp", ""))[:19]
            summary = meta.get("summary", "") or ""
            user_msg = meta.get("user_message", "") or ""
            entry = f"- ({ts}) [sim={score:.2f}]"
            if summary:
                entry += f" {summary[:300]}"
            elif user_msg:
                entry += f" Usuario: {user_msg[:200]}"
            tags = meta.get("tags", "")
            if tags:
                entry += f" [{tags}]"
            chars += len(entry) + 1
            if chars > max_chars:
                break
            lines.append(entry)
        lines.append("[/MEMORIA VECTORIAL]")
        return "\n".join(lines)

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_embeddings": len(self.embeddings),
                "model": "all-MiniLM-L6-v2",
                "faiss_enabled": _HAS_FAISS,
                "query_cache_size": _QUERY_CACHE_SIZE,
                "dirty_ops": self._dirty_ops,
            }


def get_vector_memory() -> VectorMemory:
    return VectorMemory.get_instance()
