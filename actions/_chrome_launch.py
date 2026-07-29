"""_chrome_launch.py — Legacy wrapper for _browser_launch."""
from actions._browser_launch import open_url

def chrome_launch(url: str) -> bool:
    """Launch the preferred browser (default Chrome) pointing to the specified URL."""
    return open_url(url, browser="chrome")
