"""Fast network reachability check.

Cloud calls use a 10-15 s timeout. Without this check, a device with no Wi-Fi
would make the user wait that long before falling back to offline mode.
"""
import socket
import threading
import time
from typing import Dict, Tuple
from urllib.parse import urlparse

_cache: Dict[Tuple[str, int], Tuple[float, bool]] = {}
_lock = threading.Lock()


def is_reachable(url: str, timeout: float = 1.5, ttl: float = 30.0) -> bool:
    """Return True if a TCP connection to the URL's host can be opened.

    Results are cached for `ttl` seconds so repeated scans don't pay the cost.
    """
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (80 if parsed.scheme == "http" else 443)
    key = (host, port)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ok = True
    except OSError:
        ok = False
    with _lock:
        _cache[key] = (now, ok)
    return ok


def reset_cache() -> None:
    with _lock:
        _cache.clear()
