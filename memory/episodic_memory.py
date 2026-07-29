"""
episodic_memory.py — Conversation history + episodic memory for ONYX (v2 optimized).

Optimizations:
- Shared singleton SQLite connection (WAL + synchronous=NORMAL + mmap_size)
- FTS5 virtual table for full-text search (fallback: LIKE if unsupported)
- LRU cache (OrderedDict) for recent queries + retrieve results
- Batched inserts via executemany (for bulk imports)
- Async background trim (runs outside critical path)
- Composite index (success_score, timestamp) for hybrid queries
- Rolling stats cached to avoid full-table COUNT/AVG on every call
- Hybrid semantic search via VectorMemory integration (if available)
- JSON column compression (gzip) for large tool_calls/tool_results
"""
import json
import re
import gzip
import sqlite3
import threading
import time
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

MEMORY_DIR = Path(__file__).resolve().parent
DB_PATH = MEMORY_DIR / "episodic_memory.db"
_MAX_EPISODES = 25000
_MAX_RETRIEVE = 50
_MAX_INJECT_CHARS = 10000
_COMPRESS_BYTES_THRESHOLD = 2048
_QUERY_CACHE_SIZE = 128
_RECENT_CACHE_TTL = 1.0  # seconds

_FTS_ENABLED = False


def _compress_json(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False)
    if len(raw) < _COMPRESS_BYTES_THRESHOLD:
        return "J:" + raw
    try:
        return "Z:" + gzip.compress(raw.encode("utf-8"), compresslevel=5).hex()
    except Exception:
        return "J:" + raw


def _decompress_json(s: str):
    if not isinstance(s, str):
        return s if s is not None else []
    if s.startswith("J:"):
        try:
            return json.loads(s[2:])
        except Exception:
            return []
    if s.startswith("Z:"):
        try:
            return json.loads(gzip.decompress(bytes.fromhex(s[2:])).decode("utf-8"))
        except Exception:
            return []
    try:
        return json.loads(s)
    except Exception:
        return []


class _LRUCache:
    def __init__(self, maxsize: int):
        self._data: "OrderedDict[str, tuple]" = OrderedDict()
        self._max = maxsize
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key in self._data:
                val, ts = self._data[key]
                self._data.move_to_end(key)
                if time.time() - ts > _RECENT_CACHE_TTL * 10:
                    del self._data[key]
                    return None
                return val
            return None

    def put(self, key, value):
        with self._lock:
            self._data[key] = (value, time.time())
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def invalidate(self, prefix: str = ""):
        with self._lock:
            if not prefix:
                self._data.clear()
                return
            for k in list(self._data.keys()):
                if k.startswith(prefix):
                    del self._data[k]


_query_cache = _LRUCache(_QUERY_CACHE_SIZE)
_conn_lock = threading.RLock()
_shared_conn: sqlite3.Connection | None = None
_stats_cache = {"total": 0, "avg_score": 5.0, "ts": 0.0}
_stats_lock = threading.Lock()
_trim_thread: threading.Thread | None = None
_trim_needed = threading.Event()


def _get_conn() -> sqlite3.Connection:
    global _shared_conn, _FTS_ENABLED
    if _shared_conn is not None:
        return _shared_conn
    with _conn_lock:
        if _shared_conn is not None:
            return _shared_conn
        con = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA mmap_size=268435456")
        con.execute("PRAGMA cache_size=-65536")
        con.execute("PRAGMA temp_store=MEMORY")
        con.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_message TEXT DEFAULT '',
                onyx_response TEXT DEFAULT '',
                tool_calls TEXT DEFAULT '[]',
                tool_results TEXT DEFAULT '[]',
                summary TEXT DEFAULT '',
                success_score INTEGER DEFAULT 5,
                tags TEXT DEFAULT ''
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodes_ts_desc
            ON episodes(timestamp DESC)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodes_score_ts
            ON episodes(success_score DESC, timestamp DESC)
        """)
        try:
            con.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts
                USING fts5(
                    user_message, onyx_response, summary, tags,
                    content='episodes', content_rowid='id',
                    tokenize='unicode61'
                )
            """)
            _FTS_ENABLED = True
        except sqlite3.OperationalError:
            _FTS_ENABLED = False
        con.commit()
        _shared_conn = con
        return _shared_conn


def _start_trim_daemon() -> None:
    global _trim_thread
    if _trim_thread and _trim_thread.is_alive():
        return

    def _run():
        while True:
            _trim_needed.wait(timeout=60.0)
            if _trim_needed.is_set():
                _trim_needed.clear()
            try:
                _do_trim()
            except Exception:
                pass

    _trim_thread = threading.Thread(target=_run, name="EpisodicTrim", daemon=True)
    _trim_thread.start()


def _do_trim():
    con = _get_conn()
    try:
        row = con.execute("SELECT COUNT(*) FROM episodes").fetchone()
        if row and row[0] > _MAX_EPISODES:
            excess = row[0] - _MAX_EPISODES
            con.execute(
                "DELETE FROM episodes WHERE id IN "
                "(SELECT id FROM episodes ORDER BY timestamp ASC LIMIT ?)",
                (min(excess, 2000),)
            )
            con.commit()
            _query_cache.invalidate()
            with _stats_lock:
                _stats_cache["ts"] = 0.0
    except Exception:
        pass


class EpisodicMemory:
    _lock = threading.Lock()

    def __init__(self):
        self._ensure_db()
        _start_trim_daemon()

    def _ensure_db(self):
        _get_conn()

    def record(self, user_message: str = "", onyx_response: str = "",
               tool_calls: list = None, tool_results: list = None,
               success_score: int = 5, summary: str = "", tags: str = ""):
        with self._lock:
            con = _get_conn()
            try:
                con.execute(
                    """INSERT INTO episodes (timestamp, user_message, onyx_response,
                       tool_calls, tool_results, summary, success_score, tags)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        datetime.now().isoformat(),
                        user_message[:1000],
                        onyx_response[:2000],
                        _compress_json(tool_calls or []),
                        _compress_json(tool_results or []),
                        summary[:500],
                        max(1, min(10, int(success_score))),
                        tags[:200]
                    )
                )
                con.commit()
                _trim_needed.set()
                _query_cache.invalidate()
                with _stats_lock:
                    _stats_cache["ts"] = 0.0
                try:
                    if _FTS_ENABLED:
                        new_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
                        con.execute(
                            "INSERT INTO episodes_fts(rowid, user_message, "
                            "onyx_response, summary, tags) VALUES (?,?,?,?,?)",
                            (new_id, user_message[:1000], onyx_response[:2000],
                             summary[:500], tags[:200])
                        )
                        con.commit()
                except Exception:
                    pass
            finally:
                pass

    def bulk_record(self, rows: list[dict]):
        if not rows:
            return
        payload = []
        for r in rows:
            payload.append((
                r.get("timestamp", datetime.now().isoformat()),
                str(r.get("user_message", ""))[:1000],
                str(r.get("onyx_response", ""))[:2000],
                _compress_json(r.get("tool_calls", [])),
                _compress_json(r.get("tool_results", [])),
                str(r.get("summary", ""))[:500],
                max(1, min(10, int(r.get("success_score", 5)))),
                str(r.get("tags", ""))[:200],
            ))
        with self._lock:
            con = _get_conn()
            try:
                con.executemany(
                    """INSERT INTO episodes (timestamp, user_message, onyx_response,
                       tool_calls, tool_results, summary, success_score, tags)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    payload
                )
                con.commit()
                _trim_needed.set()
                _query_cache.invalidate()
                with _stats_lock:
                    _stats_cache["ts"] = 0.0
            finally:
                pass

    def _trim(self):
        _trim_needed.set()

    def retrieve(self, query: str, max_results: int = _MAX_RETRIEVE) -> list[dict]:
        if not query:
            return []
        cache_key = f"ret:{query.lower()}:{max_results}"
        cached = _query_cache.get(cache_key)
        if cached is not None:
            return cached
        keywords = self._extract_keywords(query)
        with self._lock:
            con = _get_conn()
            try:
                rows = []
                if _FTS_ENABLED and keywords:
                    fts_query = " ".join(f'"{k}"' for k in keywords[:12] if len(k) > 1)
                    if fts_query:
                        try:
                            rows = con.execute(
                                f"""SELECT ep.* FROM episodes ep
                                    JOIN episodes_fts f ON f.rowid = ep.id
                                    WHERE episodes_fts MATCH ?
                                    ORDER BY rank
                                    LIMIT ?""",
                                (fts_query, max_results)
                            ).fetchall()
                        except Exception:
                            rows = []
                if not rows and keywords:
                    conditions = []
                    params = []
                    for kw in keywords:
                        like = f"%{kw}%"
                        conditions.append(
                            "(user_message LIKE ? OR onyx_response LIKE ? "
                            "OR summary LIKE ? OR tags LIKE ?)"
                        )
                        params.extend([like, like, like, like])
                    sql = (f"SELECT * FROM episodes WHERE "
                           f"{' OR '.join(conditions)} "
                           f"ORDER BY success_score DESC, timestamp DESC LIMIT ?")
                    params.append(max_results)
                    rows = con.execute(sql, params).fetchall()
                result = [self._row_to_dict(r) for r in rows]
                _query_cache.put(cache_key, result)
                return result
            finally:
                pass

    def retrieve_recent(self, count: int = 5) -> list[dict]:
        cache_key = f"recent:{count}"
        cached = _query_cache.get(cache_key)
        if cached is not None:
            return cached
        with self._lock:
            con = _get_conn()
            try:
                rows = con.execute(
                    "SELECT * FROM episodes ORDER BY timestamp DESC LIMIT ?",
                    (count,)
                ).fetchall()
                result = [self._row_to_dict(r) for r in rows]
                _query_cache.put(cache_key, result)
                return result
            finally:
                pass

    def get_stats(self) -> dict:
        now = time.time()
        with _stats_lock:
            if now - _stats_cache.get("ts", 0) < 30.0:
                return {
                    "total_episodes": _stats_cache["total"],
                    "avg_success_score": round(_stats_cache["avg_score"], 1),
                    "fts_enabled": _FTS_ENABLED,
                }
        with self._lock:
            con = _get_conn()
            try:
                total_row = con.execute("SELECT COUNT(*) FROM episodes").fetchone()
                total = total_row[0] if total_row else 0
                avg_row = con.execute(
                    "SELECT AVG(success_score) FROM episodes "
                    "WHERE timestamp > datetime('now', '-30 days')"
                ).fetchone()
                avg = float(avg_row[0]) if avg_row and avg_row[0] else 5.0
                with _stats_lock:
                    _stats_cache["total"] = total
                    _stats_cache["avg_score"] = avg
                    _stats_cache["ts"] = now
                return {
                    "total_episodes": total,
                    "avg_success_score_30d": round(avg, 1),
                    "fts_enabled": _FTS_ENABLED,
                }
            finally:
                pass

    def hybrid_search(self, query: str, max_results: int = 20) -> list[dict]:
        """Combine keyword + optional vector search (if available)."""
        results = {r["id"]: r for r in self.retrieve(query, max_results * 2)}
        try:
            from memory.vector_memory import get_vector_memory
            vmem = get_vector_memory()
            hits = vmem.search(query, top_k=max_results)
            for meta, _score in hits:
                eid = meta.get("episode_id")
                if eid and eid not in results:
                    results[eid] = {
                        "id": eid,
                        "timestamp": meta.get("timestamp", ""),
                        "user_message": meta.get("user_message", ""),
                        "onyx_response": "",
                        "tool_calls": [],
                        "tool_results": [],
                        "summary": meta.get("summary", ""),
                        "success_score": meta.get("success_score", 5),
                        "tags": meta.get("tags", ""),
                    }
        except Exception:
            pass
        items = sorted(
            results.values(),
            key=lambda r: (r.get("success_score", 5), r.get("timestamp", "")),
            reverse=True,
        )
        return items[:max_results]

    def format_for_prompt(self, query: str = "", recent_count: int = 3) -> str:
        if query:
            try:
                episodes = self.hybrid_search(query, max_results=_MAX_RETRIEVE)
            except Exception:
                episodes = self.retrieve(query, max_results=_MAX_RETRIEVE)
        else:
            episodes = []
        if not episodes:
            episodes = self.retrieve_recent(recent_count)
        if not episodes:
            return ""
        lines = ["[EPISODIOS RELEVANTES DEL PASADO]"]
        chars = 0
        for ep in episodes:
            entry = f"- ({str(ep.get('timestamp', ''))[:19]}) score={ep.get('success_score', 5)}"
            if ep.get("summary"):
                entry += f" {str(ep['summary'])[:300]}"
            elif ep.get("user_message"):
                entry += f" Usuario: {str(ep['user_message'])[:200]}"
            tc = ep.get("tool_calls") or []
            if tc:
                names = [c.get("name", "?") for c in tc if isinstance(c, dict)]
                if names:
                    entry += f" tools: {', '.join(names[:6])}"
            chars += len(entry) + 1
            if chars > _MAX_INJECT_CHARS:
                break
            lines.append(entry)
        lines.append("[/EPISODIOS RELEVANTES DEL PASADO]")
        return "\n".join(lines)

    def update_score(self, episode_id: int, score: int):
        with self._lock:
            con = _get_conn()
            try:
                con.execute(
                    "UPDATE episodes SET success_score=? WHERE id=?",
                    (max(1, min(10, int(score))), episode_id)
                )
                con.commit()
                _query_cache.invalidate()
                with _stats_lock:
                    _stats_cache["ts"] = 0.0
            finally:
                pass

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        text = text.lower()
        text = re.sub(r'[^a-záéíóúñü0-9\s]', ' ', text)
        words = [w.strip() for w in text.split() if len(w.strip()) > 2]
        stopwords = {
            "que", "para", "con", "por", "las", "los", "una", "uno",
            "del", "como", "más", "pero", "sus", "era", "son",
            "has", "haz", "dame", "este", "esta", "esto", "tiene",
            "puedes", "quiero", "necesito", "ser", "puede", "sobre",
            "entre", "desde", "hasta", "todo", "todos", "cuando",
            "donde", "muy", "también", "ahora", "hacer", "hace",
        }
        seen = set()
        out = []
        for w in words:
            if w not in stopwords and w not in seen:
                seen.add(w)
                out.append(w)
        return out[:64]

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {
            "id": row[0],
            "timestamp": row[1] if row[1] else "",
            "user_message": row[2] if row[2] else "",
            "onyx_response": row[3] if row[3] else "",
            "tool_calls": _decompress_json(row[4]),
            "tool_results": _decompress_json(row[5]),
            "summary": row[6] if row[6] else "",
            "success_score": int(row[7]) if row[7] else 5,
            "tags": row[8] if row[8] else "",
        }


_memory = None


def get_memory() -> EpisodicMemory:
    global _memory
    if _memory is None:
        _memory = EpisodicMemory()
    return _memory
