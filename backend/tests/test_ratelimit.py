"""Tests for the token-bucket rate limiter (Week 3.3)."""

from app.ratelimit import TokenBucket, RateLimiter


class TestTokenBucket:
    def test_should_AllowUpToCapacity_when_BurstArrives(self):
        b = TokenBucket(capacity=3, refill_per_sec=0)
        assert [b.allow() for _ in range(5)] == [True, True, True, False, False]

    def test_should_Refill_when_TimePasses(self, monkeypatch):
        t = {"now": 1000.0}
        monkeypatch.setattr("app.ratelimit.time.monotonic", lambda: t["now"])
        b = TokenBucket(capacity=2, refill_per_sec=1.0)
        assert b.allow() and b.allow()
        assert not b.allow()           # drained
        t["now"] += 1.0               # one token refilled
        assert b.allow()
        assert not b.allow()

    def test_should_NotExceedCapacity_when_IdleLong(self, monkeypatch):
        t = {"now": 0.0}
        monkeypatch.setattr("app.ratelimit.time.monotonic", lambda: t["now"])
        b = TokenBucket(capacity=2, refill_per_sec=1.0)
        t["now"] = 10_000  # huge idle
        assert b.allow() and b.allow()
        assert not b.allow()  # capped at 2, not 10_000


class TestRateLimiter:
    def test_should_IsolateKeys_when_DifferentClients(self):
        rl = RateLimiter(capacity=1, refill_per_sec=0)
        assert rl.allow("a")
        assert not rl.allow("a")   # a is drained
        assert rl.allow("b")       # b has its own bucket
