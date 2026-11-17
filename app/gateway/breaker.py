from __future__ import annotations

import time
from collections import deque


class CircuitBreaker:
    """Small, readable breaker: trip after N failures in a window, cool down, then probe."""

    def __init__(self, threshold: int = 3, window_s: int = 60, cooldown_s: int = 20):
        self.threshold = threshold
        self.window_s = window_s
        self.cooldown_s = cooldown_s
        self._failures: dict[str, deque[float]] = {}
        self._opened_at: dict[str, float] = {}
        self._half_open: set[str] = set()

    def state(self, provider: str) -> str:
        if provider in self._opened_at:
            if time.time() - self._opened_at[provider] >= self.cooldown_s:
                return "half-open"
            return "open"
        return "closed"

    def allow(self, provider: str) -> bool:
        state = self.state(provider)
        if state == "open":
            return False
        if state == "half-open":
            # Exactly one probe at a time; everyone else waits for its verdict.
            if provider in self._half_open:
                return False
            self._half_open.add(provider)
            return True
        return True

    def record_success(self, provider: str) -> None:
        self._failures.pop(provider, None)
        self._opened_at.pop(provider, None)
        self._half_open.discard(provider)

    def record_failure(self, provider: str) -> None:
        now = time.time()
        failures = self._failures.setdefault(provider, deque())
        failures.append(now)
        while failures and now - failures[0] > self.window_s:
            failures.popleft()
        if len(failures) >= self.threshold:
            self._opened_at[provider] = now
            self._half_open.discard(provider)

    def snapshot(self, provider: str) -> dict:
        now = time.time()
        failures = [t for t in self._failures.get(provider, []) if now - t <= self.window_s]
        opened_at = self._opened_at.get(provider)
        cooldown_left = 0.0
        if opened_at is not None:
            cooldown_left = max(0.0, self.cooldown_s - (now - opened_at))
        return {
            "state": self.state(provider),
            "failures_in_window": len(failures),
            "threshold": self.threshold,
            "cooldown_left_s": round(cooldown_left, 1),
        }
