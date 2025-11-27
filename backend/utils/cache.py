from redis import asyncio as aioredis
from core.config import settings
from functools import wraps
import pickle

class CacheService:
    def __init__(self):
        self.redis = aioredis.from_url(
            settings.REDIS_URL, decode_responses=False
        )

    async def get(self, key: str):
        data = await self.redis.get(key)
        return pickle.loads(data) if data else None

    async def set(self, key: str, value, ttl: int = 3600):
        await self.redis.set(
            key, 
            pickle.dumps(value),
            ex=ttl
        )

    async def clear_pattern(self, pattern: str):
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)

cache = CacheService()

def cached(ttl: int = 600, key_prefix: str = "cache"):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{key_prefix}:{func.__name__}:{args}:{kwargs}"
            cached_data = await cache.get(cache_key)
            if cached_data:
                return cached_data
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator