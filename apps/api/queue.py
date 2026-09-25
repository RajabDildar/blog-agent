"""Redis connection and RQ queue management for background generation execution."""
from __future__ import annotations

from functools import lru_cache
import redis
from rq import Queue

from apps.api.config import get_settings

settings = get_settings()


@lru_cache(maxsize=1)
def get_redis_connection() -> redis.Redis:
    """Returns a pooled, persistent Redis client connection."""
    return redis.Redis.from_url(settings.REDIS_URL)


def get_queue(name: str = "default") -> Queue:
    """Returns an RQ Queue instance bound to the shared Redis connection."""
    return Queue(name, connection=get_redis_connection())
