from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, rpm: int):
        self.rpm = rpm
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> float | None:
        """Return seconds to wait, or None when the caller may proceed."""
        if self.rpm <= 0:
            return None
        now = time.time()
        window = self._windows[key]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= self.rpm:
            return round(max(0.0, 60 - (now - window[0])), 1)
        window.append(now)
        return None

    def snapshot(self) -> dict:
        return {"rpm": self.rpm, "keys_in_window": len(self._windows)}
