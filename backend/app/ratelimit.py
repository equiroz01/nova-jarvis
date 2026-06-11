"""Lightweight in-process token-bucket rate limiting.

Even single-user, a runaway frontend retry loop or a stuck Alexa device can hammer
/chat and burn the Gemini quota + both task workers, taking NOVA down for you. This
is a reliability guard, not a multi-tenant feature — so it is a hand-rolled per-key
token bucket (no Redis, no distributed limits needed for one box).
"""

import threading
import time


class TokenBucket:
    """Classic token bucket: `capacity` tokens, refilled `refill_per_sec` per second."""

    __slots__ = ("capacity", "refill_per_sec", "_tokens", "_last")

    def __init__(self, capacity: float, refill_per_sec: float):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._tokens = capacity
        self._last = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.refill_per_sec)
        self._last = now
        if self._tokens >= cost:
            self._tokens -= cost
            return True
        return False


class RateLimiter:
    """Per-key bucket store with a single shared (capacity, refill) policy."""

    def __init__(self, capacity: float, refill_per_sec: float):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, cost: float = 1.0) -> bool:
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(self.capacity, self.refill_per_sec)
                self._buckets[key] = bucket
            return bucket.allow(cost)
