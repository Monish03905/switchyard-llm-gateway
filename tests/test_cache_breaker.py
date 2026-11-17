from __future__ import annotations

from app.gateway.breaker import CircuitBreaker
from app.gateway.cache import MemoryCache, ResponseCache, make_cache_key


async def test_memory_cache_ttl_and_clear():
    cache = MemoryCache(capacity=4)
    await cache.set("a", {"value": 1}, ttl_s=60)
    assert await cache.get("a") == {"value": 1}
    assert await cache.entries() == 1

    await cache.set("gone", {"value": 2}, ttl_s=0)
    assert await cache.get("gone") is None

    assert await cache.clear() == 1
    assert await cache.entries() == 0


async def test_memory_cache_evicts_the_least_recently_used():
    cache = MemoryCache(capacity=2)
    await cache.set("a", {"n": 1}, ttl_s=60)
    await cache.set("b", {"n": 2}, ttl_s=60)
    await cache.get("a")
    await cache.set("c", {"n": 3}, ttl_s=60)

    assert await cache.get("b") is None
    assert await cache.get("a") == {"n": 1}
    assert await cache.get("c") == {"n": 3}


async def test_response_cache_tracks_hits_and_misses():
    cache = ResponseCache(MemoryCache(capacity=8), ttl_s=60, note="test cache")
    assert await cache.get("missing") is None
    await cache.set("hit", {"text": "hello"})
    assert await cache.get("hit") == {"text": "hello"}

    stats = await cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["entries"] == 1
    assert stats["note"] == "test cache"

    purged = await cache.purge()
    assert purged["removed"] == 1
    assert (await cache.stats())["entries"] == 0
    assert (await cache.stats())["hits"] == 0


def test_cache_keys_normalise_text_and_respect_the_rail():
    messages = [{"role": "user", "content": "Hello   World"}]
    twin = [{"role": "user", "content": "hello world"}]

    first = make_cache_key("simulated", "thrift", "simulator", "sim-shunter", messages, 0.2)
    second = make_cache_key("simulated", "thrift", "simulator", "sim-shunter", twin, 0.2)
    prime = make_cache_key("simulated", "prime", "simulator", "sim-mainline", messages, 0.2)

    assert first == second
    assert first != prime


def test_breaker_trips_after_the_threshold():
    breaker = CircuitBreaker(threshold=2, window_s=60, cooldown_s=60)
    assert breaker.allow("simulator") is True
    assert breaker.state("simulator") == "closed"

    breaker.record_failure("simulator")
    assert breaker.state("simulator") == "closed"
    breaker.record_failure("simulator")

    assert breaker.state("simulator") == "open"
    assert breaker.allow("simulator") is False
    snap = breaker.snapshot("simulator")
    assert snap["state"] == "open"
    assert snap["failures_in_window"] == 2
    assert snap["cooldown_left_s"] > 0

    breaker.record_success("simulator")
    assert breaker.state("simulator") == "closed"


def test_half_open_admits_exactly_one_probe():
    breaker = CircuitBreaker(threshold=1, window_s=60, cooldown_s=0)
    breaker.record_failure("simulator")
    assert breaker.state("simulator") == "half-open"

    assert breaker.allow("simulator") is True
    assert breaker.allow("simulator") is False

    breaker.record_failure("simulator")
    assert breaker.allow("simulator") is True

    breaker.record_success("simulator")
    assert breaker.state("simulator") == "closed"
    assert breaker.allow("simulator") is True


def test_failures_age_out_of_the_window():
    breaker = CircuitBreaker(threshold=2, window_s=1, cooldown_s=60)
    breaker.record_failure("simulator")
    breaker._failures["simulator"][0] -= 5
    breaker.record_failure("simulator")
    assert breaker.state("simulator") == "closed"
