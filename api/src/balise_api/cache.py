from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from balise_api.config import get_settings

_client: Redis | None = None


def redis_client() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


async def ping() -> bool:
    try:
        return bool(await redis_client().ping())
    except Exception:
        return False


async def get_json(key: str) -> Any | None:
    try:
        raw = await redis_client().get(key)
    except Exception:
        return None
    return json.loads(raw) if raw else None


async def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        await redis_client().set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except Exception:
        return None


async def hit_rate_limit(bucket: str, limit: int, window_seconds: int = 60) -> bool:
    """Fixed-window counter. Returns True when the caller is over the limit."""
    try:
        client = redis_client()
        count = await client.incr(bucket)
        if count == 1:
            await client.expire(bucket, window_seconds)
        return bool(count > limit)
    except Exception:
        return False


async def invalidate_tiles(prefix: str = "tile:") -> int:
    client = redis_client()
    removed = 0
    async for key in client.scan_iter(match=f"{prefix}*", count=500):
        removed += await client.delete(key)
    return removed
