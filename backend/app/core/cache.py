"""Redis client wrapper with connection pooling and graceful degradation.

Synchronous implementation — the entire application uses sync SQLAlchemy,
so the cache layer must match. Every method fails gracefully when Redis is
unavailable (returns None/False/0 instead of raising).
"""

import json
import logging
from datetime import datetime, date
from typing import Any, Optional
from uuid import UUID

import redis
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------


def _json_serializer(obj: Any) -> str:
    """Serialize non-standard types for JSON storage."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _serialize(value: Any) -> str:
    """Serialize a Python value to a JSON string."""
    return json.dumps(value, default=_json_serializer)


def _deserialize(value: Optional[str]) -> Any:
    """Deserialize a JSON string, returning the raw string on failure."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _is_disabled() -> bool:
    """Quick check whether caching is administratively disabled."""
    return not settings.CACHE_ENABLED or not settings.REDIS_URL


# ---------------------------------------------------------------------------
# Redis cache singleton
# ---------------------------------------------------------------------------


class RedisCache:
    """Singleton synchronous Redis client with lazy connection and graceful degradation.

    All public methods are safe to call when Redis is down or when
    CACHE_ENABLED is False — they simply return sentinel values.
    """

    _instance: Optional["RedisCache"] = None
    _client: Optional[redis.Redis] = None

    def __new__(cls) -> "RedisCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # -- metrics (thread-safe enough for approximate counters) ----------
    hit_count: int = 0
    miss_count: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0

    # -- connection management ------------------------------------------

    def _get_client(self) -> Optional[redis.Redis]:
        """Get or create the Redis client (lazy init)."""
        if _is_disabled():
            return None

        if self._client is None:
            try:
                self._client = redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=20,
                    retry_on_timeout=True,
                    health_check_interval=30,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                self._client.ping()
                logger.info("Connected to Redis at %s", settings.REDIS_URL)
            except (ConnectionError, TimeoutError, RedisError, OSError) as e:
                logger.warning(
                    "Failed to connect to Redis at %s: %s. Caching disabled.",
                    settings.REDIS_URL,
                    e,
                )
                self._client = None
        return self._client

    # -- core operations ------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a deserialized value. Returns None on miss or error."""
        try:
            client = self._get_client()
            if client is None:
                return None
            raw = client.get(key)
            if raw is None:
                self.miss_count += 1
                logger.debug("CACHE MISS %s", key)
                return None
            self.hit_count += 1
            logger.debug("CACHE HIT %s", key)
            return _deserialize(raw)
        except (ConnectionError, TimeoutError, RedisError, OSError) as e:
            logger.warning("CACHE ERROR get %s: %s", key, e)
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store a JSON-serialized value with optional TTL (seconds)."""
        try:
            client = self._get_client()
            if client is None:
                return False
            effective_ttl = ttl if ttl is not None else settings.CACHE_DEFAULT_TTL
            serialized = _serialize(value)
            result = client.setex(key, effective_ttl, serialized)
            logger.debug("CACHE SET %s (ttl=%s)", key, effective_ttl)
            return bool(result)
        except (ConnectionError, TimeoutError, RedisError, OSError) as e:
            logger.warning("CACHE ERROR set %s: %s", key, e)
            return False

    def delete(self, key: str) -> bool:
        """Delete a single key. Returns True if the key existed."""
        try:
            client = self._get_client()
            if client is None:
                return False
            result = client.delete(key)
            if result:
                logger.debug("CACHE DELETE %s", key)
            return result > 0
        except (ConnectionError, TimeoutError, RedisError, OSError) as e:
            logger.warning("CACHE ERROR delete %s: %s", key, e)
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern (SCAN-based)."""
        try:
            client = self._get_client()
            if client is None:
                return 0
            keys: list[str] = []
            cursor = 0
            while True:
                cursor, batch = client.scan(cursor=cursor, match=pattern, count=1000)
                keys.extend(batch)
                if cursor == 0:
                    break
            if keys:
                deleted = client.delete(*keys)
                logger.debug("CACHE DELETE pattern %s: %s keys", pattern, deleted)
                return deleted
            return 0
        except (ConnectionError, TimeoutError, RedisError, OSError) as e:
            logger.warning("CACHE ERROR delete_pattern %s: %s", pattern, e)
            return 0

    def exists(self, key: str) -> bool:
        """Check whether a key exists in Redis."""
        try:
            client = self._get_client()
            if client is None:
                return False
            return client.exists(key) > 0
        except (ConnectionError, TimeoutError, RedisError, OSError) as e:
            logger.warning("CACHE ERROR exists %s: %s", key, e)
            return False

    def ttl(self, key: str) -> int:
        """Get remaining TTL in seconds (-2 = key missing, -1 = no expiry)."""
        try:
            client = self._get_client()
            if client is None:
                return -2
            return client.ttl(key)
        except (ConnectionError, TimeoutError, RedisError, OSError) as e:
            logger.warning("CACHE ERROR ttl %s: %s", key, e)
            return -2

    def close(self) -> None:
        """Close the Redis connection pool explicitly."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def flush_metrics(self) -> dict[str, Any]:
        """Return current metrics and reset counters."""
        stats = {
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "hit_rate": round(self.hit_rate, 4),
        }
        self.hit_count = 0
        self.miss_count = 0
        return stats


# Global singleton — import this from anywhere in the app.
redis_cache = RedisCache()
