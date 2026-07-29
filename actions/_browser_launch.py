"""_browser_launch.py — Open URLs in the user's preferred browser."""
import subprocess
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PREFS_PATH = BASE_DIR / "config" / "browser_pref.json"

# Browser name → list of possible start commands
_BROWSER_COMMANDS = {
    "chrome":      [r'"C:\Program Files\Google\Chrome\Application\chrome.exe"',
                    r'"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"',
                    "chrome"],
    "google chrome": [r'"C:\Program Files\Google\Chrome\Application\chrome.exe"',
                      r'"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"',
                      "chrome"],
    "edge":        [r'"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"',
                    r'"C:\Program Files\Microsoft\Edge\Application\msedge.exe"',
                    "msedge"],
    "microsoft edge": [r'"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"',
                       r'"C:\Program Files\Microsoft\Edge\Application\msedge.exe"',
                       "msedge"],
    "firefox":     [r'"C:\Program Files\Mozilla Firefox\firefox.exe"',
                    r'"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"',
                    "firefox"],
    "brave":       [r'"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"',
                    "brave"],
    "opera":       [r'"C:\Program Files\Opera\launcher.exe"',
                    "opera"],
}

_DISPLAY_NAMES = {
    "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "edge": "Microsoft Edge", "microsoft edge": "Microsoft Edge",
    "firefox": "Mozilla Firefox",
    "brave": "Brave",
    "opera": "Opera",
}


def _load_pref() -> str:
    """Load the user's preferred browser name, or empty string for system default."""
    try:
        if PREFS_PATH.exists():
            data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
            return data.get("preferred_browser", "").strip().lower()
    except Exception:
        pass
    return ""


def _save_pref(browser: str):
    PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREFS_PATH.write_text(json.dumps({"preferred_browser": browser.lower().strip()}, indent=2), encoding="utf-8")


def _find_browser_window(browser_keywords: list[str] = None):
    """Find an open browser window by title keywords."""
    if browser_keywords is None:
        browser_keywords = ["Chrome", "Edge", "Firefox", "Brave", "Opera"]
    try:
        import pygetwindow as gw
        for win in gw.getAllWindows():
            if win.title.strip():
                for kw in browser_keywords:
                    if kw.lower() in win.title.lower():
                        return win
    except Exception:
        pass
    return None


def set_preferred_browser(browser: str) -> str:
    """Set the preferred browser for opening URLs."""
    name = browser.lower().strip()
    if name not in _BROWSER_COMMANDS:
        known = ", ".join(sorted(set(k for k in _BROWSER_COMMANDS.keys() if " " not in k)))
        return f"Navegador no reconocido. Usá uno de: {known}"
    _save_pref(name)
    display = _DISPLAY_NAMES.get(name, name.title())
    return f"Navegador preferido cambiado a {display}. Voy a usar {display} para abrir enlaces."


def get_preferred_browser() -> str:
    """Get the display name of the preferred browser."""
    pref = _load_pref()
    return _DISPLAY_NAMES.get(pref, "chrome")


def open_url(url: str, browser: str = "") -> bool:
    """
    Open a URL in the specified browser (or the preferred one, or system default).
    Returns True if successful.
    """
    if not browser:
        browser = _load_pref()
    name = browser.lower().strip()

    if name and name in _BROWSER_COMMANDS:
        for cmd in _BROWSER_COMMANDS[name]:
            try:
                subprocess.Popen(f'start "" {cmd} "{url}"', shell=True)
                time.sleep(0.5)
                return True
            except Exception:
                continue

    # Fallback: system default browser
    try:
        import webbrowser
        webbrowser.open(url, new=2)
        return True
    except Exception:
        return False
