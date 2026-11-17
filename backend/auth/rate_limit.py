"""
Failed-login limiter — slows down password guessing.
Counts failures per key (an email or an IP) in a sliding time window.
In-memory, so it's per process: fine for one uvicorn worker; use Redis if you run several.
"""

import threading
import time
from collections import deque


class LoginLimiter:
    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque] = {}   # key → timestamps of recent failures
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque:
        """Drop failures older than the window; returns what's left."""
        q = self._failures.get(key, deque())
        while q and now - q[0] > self.window:
            q.popleft()
        if not q:
            self._failures.pop(key, None)
        return q

    def retry_after(self, key: str) -> int:
        """Seconds until this key may try again, or 0 if it isn't blocked."""
        now = time.monotonic()
        with self._lock:
            q = self._recent(key, now)
            if len(q) < self.max_failures:
                return 0
            return int(self.window - (now - q[0])) + 1

    def record_failure(self, key: str):
        now = time.monotonic()
        with self._lock:
            self._recent(key, now)
            self._failures.setdefault(key, deque()).append(now)

    def reset(self, key: str):
        with self._lock:
            self._failures.pop(key, None)


# 5 wrong passwords per account per 15 min. The IP limit is higher because a
# whole college often shares one public IP.
email_limiter = LoginLimiter(max_failures=5, window_seconds=15 * 60)
ip_limiter    = LoginLimiter(max_failures=50, window_seconds=15 * 60)
