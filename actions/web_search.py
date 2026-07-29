"""web_search.py — Búsqueda web real y extracción de contenido via DuckDuckGo + BeautifulSoup."""

import re
import requests
from bs4 import BeautifulSoup

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_HEADERS = {"User-Agent": _USER_AGENT}
_TIMEOUT = 30


def _ddg_search(query: str, max_results: int = 10) -> list[dict]:
    """Search DuckDuckGo and return list of {title, snippet, url}."""
    try:
        from ddgs import DDGS
        with DDGS() as search:
            raw = list(search.text(query, max_results=max_results))
        out = []
        for r in raw:
            out.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", ""),
            })
        if out:
            return out
    except Exception:
        pass
    try:
        from duckduckgo_search import DDGS
        with DDGS() as search:
            raw = list(search.text(query, max_results=max_results))
        out = []
        for r in raw:
            out.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", ""),
            })
        if out:
            return out
    except Exception:
        pass
    fallback_url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
    try:
        resp = requests.get(fallback_url, headers=_HEADERS, timeout=_TIMEOUT)
        soup = BeautifulSoup(resp.text, "html.parser")
        raw = soup.select(".result")
        out = []
        for r in raw[:max_results]:
            title_el = r.select_one(".result__title a")
            snippet_el = r.select_one(".result__snippet")
            out.append({
                "title": title_el.get_text(strip=True) if title_el else "",
                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                "url": title_el.get("href", "") if title_el else "",
            })
        return out
    except Exception:
        return []


def _extract_text(url: str) -> str:
    """Fetch a URL and extract readable main text."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        for candidate in ["article", "main", ".post-content", ".entry-content",
                          ".article-body", "#content", ".content"]:
            container = soup.select_one(candidate)
            if container:
                texts = container.find_all(["p", "h1", "h2", "h3", "h4", "li"])
                break
        else:
            texts = soup.find_all(["p", "h1", "h2", "h3", "h4"])
        lines = []
        for t in texts:
            txt = t.get_text(strip=True)
            if txt and len(txt) > 20:
                lines.append(txt)
        result = "\n\n".join(lines)
        if not result or len(result) < 50:
            result = soup.get_text(separator="\n", strip=True)
            lines2 = [l for l in result.split("\n") if len(l.strip()) > 30]
            result = "\n\n".join(lines2[:400])
        return result[:80000]
    except Exception:
        return ""


def web_search(parameters: dict, player=None) -> str:
    """Search the web and optionally fetch full content from the top result."""
    query = parameters.get("query", "").strip()
    mode = parameters.get("mode", "search")
    fetch_content = parameters.get("fetch_content", False)

    if not query:
        return "Proporciona una consulta de búsqueda."

    results = _ddg_search(query, max_results=10)
    if not results:
        return f"No se encontraron resultados para '{query}'."

    lines = [f"Resultados de búsqueda para '{query}':"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n{i}. {r['title']}")
        lines.append(f"   {r['snippet']}")
        lines.append(f"   {r['url']}")

    if fetch_content and results:
        url = results[0]["url"]
        content = _extract_text(url)
        if content:
            lines.append(f"\n\n--- Contenido de {results[0]['title']} ---\n")
            lines.append(content[:8000])

    return "\n".join(lines)


def web_search_raw(query: str, max_results: int = 3) -> list[dict]:
    """Convenience: return raw search results list."""
    return _ddg_search(query, max_results)


def fetch_article_text(url: str) -> str:
    """Convenience: fetch and extract text from a URL."""
    return _extract_text(url)
