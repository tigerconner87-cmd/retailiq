"""Simple Redis cache wrapper for dashboard endpoints."""

import json
import logging
from functools import wraps

import redis
from app.config import settings

log = logging.getLogger(__name__)

_client = None


def _get_redis():
    global _client
    if _client is None:
        try:
            _client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2)
            _client.ping()
            log.info("Redis connected")
        except Exception:
            log.warning("Redis not available — caching disabled")
            _client = None
    return _client


def cache_get(key: str):
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.get(key)
        return json.loads(data) if data else None
    except Exception:
        return None


def cache_set(key: str, value, ttl: int = 60):
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


def cached(prefix: str, ttl: int = 60):
    """Decorator: cache a function result by prefix + first arg (shop_id)."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract shop_id from args (typically second arg after db)
            shop_id = args[1] if len(args) > 1 else kwargs.get("shop_id", "")
            key = f"riq:{prefix}:{shop_id}"
            hit = cache_get(key)
            if hit is not None:
                return hit
            result = func(*args, **kwargs)
            cache_set(key, result, ttl)
            return result
        return wrapper
    return decorator
