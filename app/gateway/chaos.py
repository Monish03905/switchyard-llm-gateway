from __future__ import annotations

import time


class Squall:
    """A named, deliberate outage. Arm it from the switchboard and watch the fallback rail."""

    def __init__(self) -> None:
        self.remaining = 0
        self.armed_at: float | None = None

    def arm(self, fails: int) -> dict:
        self.remaining = max(0, min(10, int(fails)))
        self.armed_at = time.time() if self.remaining else None
        return self.snapshot()

    def take(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        if self.remaining == 0:
            self.armed_at = None
        return True

    def snapshot(self) -> dict:
        return {
            "armed": self.remaining,
            "armed_at": self.armed_at,
            "shape": "simulated provider failures, one attempt each",
        }
