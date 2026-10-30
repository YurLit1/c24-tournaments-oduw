"""Redis shared by all instances: rate limits (D2.1), revoked tokens (D3.1), login attempts (D3.3),
the user -> gateway registry and presence (D5.1, D5.2).

    r = cache.client()
    await r.set("presence:u1", "gateway-a", ex=30)
"""

from redis.asyncio import Redis

from . import config

_client: Redis | None = None


def client() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(config.REDIS_URL, decode_responses=True)
    return _client


async def close() -> None:
    if _client is not None:
        await _client.aclose()
