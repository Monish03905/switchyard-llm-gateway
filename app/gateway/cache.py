from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class CacheEntry:
    expires_at: float
    payload: dict


class MemoryCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._data: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> dict | None:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.time():
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return entry.payload

    async def set(self, key: str, payload: dict, ttl_s: int) -> None:
        async with self._lock:
            self._data[key] = CacheEntry(time.time() + ttl_s, payload)
            self._data.move_to_end(key)
            while len(self._data) > self.capacity:
                self._data.popitem(last=False)

    async def entries(self) -> int:
        return len(self._data)

    async def clear(self) -> int:
        async with self._lock:
            count = len(self._data)
            self._data.clear()
            return count

    async def close(self) -> None:
        return None


class RedisCache:
    def __init__(self, client):
        self.client = client
        self.prefix = "switchyard:cache:"

    async def get(self, key: str) -> dict | None:
        raw = await self.client.get(self.prefix + key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set(self, key: str, payload: dict, ttl_s: int) -> None:
        await self.client.set(self.prefix + key, json.dumps(payload), ex=ttl_s)

    async def entries(self) -> int:
        try:
            return int(await self.client.dbsize())
        except Exception:
            return -1

    async def clear(self) -> int:
        removed = 0
        async for key in self.client.scan_iter(match=self.prefix + "*", count=200):
            removed += int(await self.client.delete(key) or 0)
        return removed

    async def close(self) -> None:
        await self.client.aclose()


class ResponseCache:
    def __init__(self, backend, ttl_s: int, note: str = ""):
        self.backend = backend
        self.ttl_s = ttl_s
        self.note = note
        self.hits = 0
        self.misses = 0

    async def get(self, key: str) -> dict | None:
        payload = await self.backend.get(key)
        if payload is None:
            self.misses += 1
            return None
        self.hits += 1
        return payload

    async def set(self, key: str, payload: dict) -> None:
        await self.backend.set(key, payload, self.ttl_s)

    async def stats(self) -> dict:
        return {
            "entries": await self.backend.entries(),
            "hits": self.hits,
            "misses": self.misses,
            "ttl_s": self.ttl_s,
            "note": self.note,
        }

    async def purge(self) -> dict:
        removed = await self.backend.clear()
        self.hits = 0
        self.misses = 0
        return {"removed": removed, "note": "Cache purged. The next request pays full fare."}

    async def close(self) -> None:
        await self.backend.close()


def make_cache_key(
    mode: str,
    tier: str,
    provider: str,
    model: str,
    messages: list[dict],
    temperature: float | None,
    tools_signature: str = "",
) -> str:
    normalized = [
        {
            "role": str(message.get("role", "")),
            "content": " ".join(str(message.get("content", "")).lower().split()),
        }
        for message in messages
    ]
    material = json.dumps(
        {
            "v": 1,
            "mode": mode,
            "tier": tier,
            "provider": provider,
            "model": model,
            "messages": normalized,
            "temperature": temperature,
            "tools": tools_signature,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def build_cache(settings) -> ResponseCache:
    if settings.redis_url:
        try:
            from redis.asyncio import Redis

            client = Redis.from_url(
                settings.redis_url, encoding="utf-8", decode_responses=True, socket_timeout=1.5
            )
            await client.ping()
            return ResponseCache(
                RedisCache(client),
                settings.cache_ttl_s,
                note="Redis-backed response cache",
            )
        except Exception:
            pass
    return ResponseCache(
        MemoryCache(settings.cache_max_entries),
        settings.cache_ttl_s,
        note="In-process response cache (set REDIS_URL to share it across workers)",
    )
