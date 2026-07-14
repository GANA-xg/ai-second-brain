"""
Tests for the Redis cache layer (Part 11).

All tests mock the underlying Redis client so no running Redis is required.
The singleton RedisCache instance is properly reset between tests by calling
.close() and resetting metrics counters on the existing instance.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import ConnectionError, TimeoutError

from app.core.cache import RedisCache, redis_cache
from app.core.cache_keys import (
    conversation_list_key,
    conversation_messages_key,
    document_list_key,
    memory_list_key,
    search_key,
)
from app.core.config import settings
from app.models.memory import MemoryType
from app.services.cache_service import (
    cache_service,
    invalidate_conversation_cache,
    invalidate_document_cache,
    invalidate_memory_cache,
    invalidate_message_cache,
    invalidate_search_cache,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _reset_singleton():
    """Reset the singleton instance state WITHOUT destroying the instance.

    We cannot set RedisCache._instance = None because the module-level
    ``redis_cache`` variable already holds a reference to the old instance.
    Instead we close the client and reset counters on the existing instance.
    """
    redis_cache.close()
    redis_cache.hit_count = 0
    redis_cache.miss_count = 0


def _make_mock_client():
    """Build a standard mock Redis client with all defaults."""
    mc = MagicMock()
    mc.ping.return_value = True
    mc.get.return_value = None  # default: cache miss
    mc.setex.return_value = True
    mc.delete.return_value = 1
    mc.scan.return_value = (0, [])
    mc.exists.return_value = 1
    mc.ttl.return_value = 60
    return mc


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset singleton state before and after every test."""
    _reset_singleton()
    yield
    _reset_singleton()


@pytest.fixture(autouse=True)
def ensure_cache_enabled():
    """Force caching on for every test that does not test disablement."""
    orig = settings.CACHE_ENABLED
    settings.CACHE_ENABLED = True
    yield
    settings.CACHE_ENABLED = orig


# ---------------------------------------------------------------------------
# Helper: context manager that patches redis.from_url and returns a mock client
# ---------------------------------------------------------------------------


def _patch_redis(mock_client=None):
    """Patch ``app.core.cache.redis.from_url`` and return the mock client.

    ``cache.py`` calls ``redis.from_url(…)`` (a module-level alias for
    ``Redis.from_url``) inside ``_get_client()``.  We must patch the
    *module-level name* ``redis.from_url``, NOT the class method
    ``redis.Redis.from_url`` – they are separate bindings.
    """
    if mock_client is None:
        mock_client = _make_mock_client()
    return patch("app.core.cache.redis.from_url", return_value=mock_client)


# ═════════════════════════════════════════════════════════════════════════════
# Core Redis operations
# ═════════════════════════════════════════════════════════════════════════════


class TestRedisGet:
    """redis_cache.get()"""

    def test_cache_miss_returns_none(self):
        mc = _make_mock_client()
        mc.get.return_value = None
        with _patch_redis(mc):
            result = redis_cache.get("test:key")
        assert result is None
        assert redis_cache.hit_rate == 0.0

    def test_cache_hit_returns_deserialized_value(self):
        mc = _make_mock_client()
        mc.get.return_value = json.dumps({"name": "Alice"})
        with _patch_redis(mc):
            result = redis_cache.get("test:key")
        assert result == {"name": "Alice"}
        assert redis_cache.hit_rate == 1.0

    def test_returns_none_on_redis_error(self):
        mc = _make_mock_client()
        mc.get.side_effect = ConnectionError("down")
        with _patch_redis(mc):
            result = redis_cache.get("test:key")
        assert result is None

    def test_graceful_degradation_when_disabled(self):
        settings.CACHE_ENABLED = False
        assert redis_cache.get("any:key") is None


class TestRedisSet:
    """redis_cache.set()"""

    def test_set_stores_serialized_value(self):
        mc = _make_mock_client()
        with _patch_redis(mc):
            result = redis_cache.set("test:key", {"data": 42}, ttl=120)
        assert result is True
        mc.setex.assert_called_once_with("test:key", 120, json.dumps({"data": 42}))

    def test_set_uses_default_ttl(self):
        mc = _make_mock_client()
        with _patch_redis(mc):
            redis_cache.set("test:key", "x")
        mc.setex.assert_called_once()
        _, ttl_arg, _ = mc.setex.call_args[0]
        assert ttl_arg == settings.CACHE_DEFAULT_TTL

    def test_returns_false_on_redis_error(self):
        mc = _make_mock_client()
        mc.setex.side_effect = TimeoutError("timeout")
        with _patch_redis(mc):
            result = redis_cache.set("test:key", "x")
        assert result is False

    def test_graceful_degradation_when_disabled(self):
        settings.CACHE_ENABLED = False
        assert redis_cache.set("k", "v") is False


class TestRedisDelete:
    """redis_cache.delete()"""

    def test_delete_existing_key(self):
        mc = _make_mock_client()
        mc.delete.return_value = 1
        with _patch_redis(mc):
            assert redis_cache.delete("test:key") is True

    def test_delete_missing_key(self):
        mc = _make_mock_client()
        mc.delete.return_value = 0
        with _patch_redis(mc):
            assert redis_cache.delete("test:key") is False

    def test_returns_false_on_redis_error(self):
        mc = _make_mock_client()
        mc.delete.side_effect = ConnectionError("down")
        with _patch_redis(mc):
            assert redis_cache.delete("test:key") is False

    def test_graceful_degradation_when_disabled(self):
        settings.CACHE_ENABLED = False
        assert redis_cache.delete("k") is False


class TestRedisDeletePattern:
    """redis_cache.delete_pattern()"""

    def test_delete_pattern_scan_and_delete(self):
        mc = _make_mock_client()
        mc.scan.return_value = (0, ["a", "b", "c"])
        mc.delete.return_value = 3
        with _patch_redis(mc):
            count = redis_cache.delete_pattern("test:*")
        assert count == 3
        mc.scan.assert_called()
        mc.delete.assert_called_once_with("a", "b", "c")

    def test_delete_pattern_no_matches(self):
        mc = _make_mock_client()
        mc.scan.return_value = (0, [])
        with _patch_redis(mc):
            assert redis_cache.delete_pattern("nomatch:*") == 0

    def test_multiple_scan_pages(self):
        """Verify SCAN cursor loops over multiple pages."""
        mc = _make_mock_client()
        mc.scan.side_effect = [(1, ["k1", "k2"]), (0, ["k3"])]
        mc.delete.return_value = 3  # 3 keys deleted
        with _patch_redis(mc):
            count = redis_cache.delete_pattern("k:*")
        assert count == 3
        assert mc.delete.call_count == 1

    def test_returns_zero_on_redis_error(self):
        mc = _make_mock_client()
        mc.scan.side_effect = ConnectionError("down")
        with _patch_redis(mc):
            assert redis_cache.delete_pattern("test:*") == 0

    def test_graceful_degradation_when_disabled(self):
        settings.CACHE_ENABLED = False
        assert redis_cache.delete_pattern("*") == 0


class TestRedisExists:
    """redis_cache.exists()"""

    def test_exists_true(self):
        mc = _make_mock_client()
        mc.exists.return_value = 1
        with _patch_redis(mc):
            assert redis_cache.exists("test:key") is True

    def test_exists_false(self):
        mc = _make_mock_client()
        mc.exists.return_value = 0
        with _patch_redis(mc):
            assert redis_cache.exists("test:key") is False

    def test_returns_false_on_redis_error(self):
        mc = _make_mock_client()
        mc.exists.side_effect = TimeoutError("timeout")
        with _patch_redis(mc):
            assert redis_cache.exists("test:key") is False

    def test_graceful_degradation_when_disabled(self):
        settings.CACHE_ENABLED = False
        assert redis_cache.exists("k") is False


class TestRedisTTL:
    """redis_cache.ttl()"""

    def test_ttl_remaining(self):
        mc = _make_mock_client()
        mc.ttl.return_value = 45
        with _patch_redis(mc):
            assert redis_cache.ttl("test:key") == 45

    def test_ttl_missing_key(self):
        mc = _make_mock_client()
        mc.ttl.return_value = -2
        with _patch_redis(mc):
            assert redis_cache.ttl("test:key") == -2

    def test_ttl_no_expiry(self):
        mc = _make_mock_client()
        mc.ttl.return_value = -1
        with _patch_redis(mc):
            assert redis_cache.ttl("test:key") == -1

    def test_graceful_degradation_when_disabled(self):
        settings.CACHE_ENABLED = False
        assert redis_cache.ttl("k") == -2


# ═════════════════════════════════════════════════════════════════════════════
# Serialization
# ═════════════════════════════════════════════════════════════════════════════


class TestSerialization:
    """JSON serialization of special types (UUID, datetime, nested)."""

    def test_uuid_in_value_produces_string(self):
        mc = _make_mock_client()
        with _patch_redis(mc):
            uid = uuid.uuid4()
            redis_cache.set("test:uuid", {"id": uid})
        args = mc.setex.call_args[0]
        stored = json.loads(args[2])
        assert stored["id"] == str(uid)

    def test_datetime_in_value_produces_isoformat(self):
        mc = _make_mock_client()
        with _patch_redis(mc):
            now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
            redis_cache.set("test:dt", {"ts": now})
        args = mc.setex.call_args[0]
        stored = json.loads(args[2])
        assert stored["ts"] == "2026-07-10T12:00:00+00:00"

    def test_nested_structures_roundtrip(self):
        mc = _make_mock_client()
        data = {"items": [1, 2, 3], "meta": {"v": 2}}
        mc.get.return_value = json.dumps(data)
        with _patch_redis(mc):
            redis_cache.set("k", data)
            result = redis_cache.get("k")
        assert result == data

    def test_raw_string_roundtrip(self):
        mc = _make_mock_client()
        mc.get.return_value = '"hello"'
        with _patch_redis(mc):
            redis_cache.set("k", "hello")
            result = redis_cache.get("k")
        assert result == "hello"

    def test_none_serialized_as_json_null(self):
        mc = _make_mock_client()
        with _patch_redis(mc):
            redis_cache.set("k", None)
        args = mc.setex.call_args[0]
        assert args[2] == "null"

    def test_list_of_objects_roundtrip(self):
        mc = _make_mock_client()
        data = [{"id": 1, "val": "a"}, {"id": 2, "val": "b"}]
        mc.get.return_value = json.dumps(data)
        with _patch_redis(mc):
            redis_cache.set("k", data)
            result = redis_cache.get("k")
        assert result == data
        assert len(result) == 2


# ═════════════════════════════════════════════════════════════════════════════
# Metrics
# ═════════════════════════════════════════════════════════════════════════════


class TestCacheMetrics:
    """Cache hit/miss tracking and flush_metrics()."""

    def test_hit_tracked(self):
        mc = _make_mock_client()
        mc.get.return_value = '"v"'
        with _patch_redis(mc):
            redis_cache.get("k")
        assert redis_cache.hit_count == 1
        assert redis_cache.miss_count == 0

    def test_miss_tracked(self):
        mc = _make_mock_client()
        mc.get.return_value = None
        with _patch_redis(mc):
            redis_cache.get("k")
        assert redis_cache.hit_count == 0
        assert redis_cache.miss_count == 1

    def test_hit_rate_mixed(self):
        mc = _make_mock_client()
        with _patch_redis(mc):
            mc.get.return_value = None
            redis_cache.get("k1")
            mc.get.return_value = '"v"'
            redis_cache.get("k2")
        assert redis_cache.hit_count == 1
        assert redis_cache.miss_count == 1
        assert round(redis_cache.hit_rate, 2) == 0.5

    def test_flush_metrics_resets_counters(self):
        mc = _make_mock_client()
        mc.get.return_value = '"v"'
        with _patch_redis(mc):
            redis_cache.get("k")
            stats = redis_cache.flush_metrics()
        assert stats["hit_count"] == 1
        assert stats["hit_rate"] == 1.0
        assert redis_cache.hit_count == 0
        assert redis_cache.miss_count == 0

    def test_hit_rate_zero_when_no_ops(self):
        assert redis_cache.hit_rate == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Graceful degradation
# ═════════════════════════════════════════════════════════════════════════════


class TestGracefulDegradation:
    """All operations degrade gracefully when Redis is unreachable."""

    def test_ping_failure_disables_cache(self):
        """When ping() fails, the client is set to None."""
        mc = MagicMock()
        mc.ping.side_effect = ConnectionError("refused")
        with _patch_redis(mc):
            result = redis_cache.get("k")
        assert result is None
        assert redis_cache._client is None

    def test_lazy_init_happens_on_first_call(self):
        """Client is NOT created until first operation."""
        assert redis_cache._client is None
        mc = _make_mock_client()
        with _patch_redis(mc):
            redis_cache.get("k")
        # After the 'with', the mock is still set as _client because
        # _get_client stored it
        assert redis_cache._client is not None  # noqa

    def test_oserror_during_get_returns_none(self):
        mc = MagicMock()
        mc.ping.side_effect = OSError("connection reset")
        with _patch_redis(mc):
            result = redis_cache.get("k")
        assert result is None

    def test_all_ops_return_safe_defaults_when_disabled(self):
        settings.CACHE_ENABLED = False
        assert redis_cache.get("k") is None
        assert redis_cache.set("k", "v") is False
        assert redis_cache.delete("k") is False
        assert redis_cache.delete_pattern("k:*") == 0
        assert redis_cache.exists("k") is False
        assert redis_cache.ttl("k") == -2


# ═════════════════════════════════════════════════════════════════════════════
# Cache key generation
# ═════════════════════════════════════════════════════════════════════════════


class TestCacheKeyGeneration:
    """Cache key format consistency."""

    def test_search_key_format(self):
        uid = uuid.UUID("11111111-1111-1111-1111-111111111111")
        key = search_key(uid, "what is AI?")
        assert key.startswith("search:11111111-1111-1111-1111-111111111111:")

    def test_search_key_deterministic(self):
        uid = uuid.uuid4()
        q = "same query"
        assert search_key(uid, q) == search_key(uid, q)

    def test_search_key_differs_by_query(self):
        uid = uuid.uuid4()
        assert search_key(uid, "hello") != search_key(uid, "world")

    def test_search_key_differs_by_user(self):
        q = "same"
        assert search_key(uuid.uuid4(), q) != search_key(uuid.uuid4(), q)

    def test_document_key_format(self):
        uid = uuid.UUID("22222222-2222-2222-2222-222222222222")
        assert document_list_key(uid) == "docs:22222222-2222-2222-2222-222222222222"

    def test_memory_key_format(self):
        uid = uuid.UUID("33333333-3333-3333-3333-333333333333")
        assert memory_list_key(uid).startswith("memories:33333333-3333-3333-3333-333333333333:")

    def test_memory_key_differs_by_type(self):
        uid = uuid.uuid4()
        assert memory_list_key(uid, MemoryType.FACT) != memory_list_key(uid, MemoryType.GOAL)

    def test_memory_key_differs_by_active(self):
        uid = uuid.uuid4()
        assert memory_list_key(uid, is_active=True) != memory_list_key(uid, is_active=False)

    def test_conversation_key_format(self):
        uid = uuid.UUID("44444444-4444-4444-4444-444444444444")
        assert conversation_list_key(uid) == "conversations:44444444-4444-4444-4444-444444444444"

    def test_messages_key_format(self):
        cid = uuid.UUID("55555555-5555-5555-5555-555555555555")
        assert conversation_messages_key(cid, 1, 20) == "messages:55555555-5555-5555-5555-555555555555:1:20"

    def test_messages_key_differs_by_page(self):
        cid = uuid.uuid4()
        assert conversation_messages_key(cid, 1, 20) != conversation_messages_key(cid, 2, 20)

    def test_messages_key_differs_by_page_size(self):
        cid = uuid.uuid4()
        assert conversation_messages_key(cid, 1, 20) != conversation_messages_key(cid, 1, 50)


# ═════════════════════════════════════════════════════════════════════════════
# Cross-user isolation
# ═════════════════════════════════════════════════════════════════════════════


class TestCrossUserIsolation:
    """Keys are scoped by user; one user cannot see another user's data."""

    def test_document_keys_differ(self):
        assert document_list_key(uuid.uuid4()) != document_list_key(uuid.uuid4())

    def test_conversation_keys_differ(self):
        assert conversation_list_key(uuid.uuid4()) != conversation_list_key(uuid.uuid4())

    def test_search_keys_differ(self):
        assert search_key(uuid.uuid4(), "q") != search_key(uuid.uuid4(), "q")

    def test_memory_keys_differ(self):
        assert memory_list_key(uuid.uuid4()) != memory_list_key(uuid.uuid4())


# ═════════════════════════════════════════════════════════════════════════════
# CacheService wrapper delegation
# ═════════════════════════════════════════════════════════════════════════════


class TestCacheServiceWrapper:
    """CacheService correctly delegates every method to RedisCache."""

    def test_get_delegates(self):
        with patch.object(redis_cache, "get", return_value="x") as m:
            assert cache_service.get("k") == "x"
        m.assert_called_once_with("k")

    def test_set_delegates(self):
        with patch.object(redis_cache, "set", return_value=True) as m:
            assert cache_service.set("k", "v", ttl=60) is True
        m.assert_called_once_with("k", "v", 60)

    def test_delete_delegates(self):
        with patch.object(redis_cache, "delete", return_value=True) as m:
            assert cache_service.delete("k") is True
        m.assert_called_once_with("k")

    def test_delete_pattern_delegates(self):
        with patch.object(redis_cache, "delete_pattern", return_value=3) as m:
            assert cache_service.delete_pattern("p:*") == 3
        m.assert_called_once_with("p:*")

    def test_exists_delegates(self):
        with patch.object(redis_cache, "exists", return_value=True) as m:
            assert cache_service.exists("k") is True
        m.assert_called_once_with("k")

    def test_ttl_delegates(self):
        with patch.object(redis_cache, "ttl", return_value=30) as m:
            assert cache_service.ttl("k") == 30
        m.assert_called_once_with("k")

    def test_hit_rate_property(self):
        redis_cache.hit_count = 3
        redis_cache.miss_count = 1
        assert cache_service.hit_rate == 0.75

    def test_flush_metrics_delegates(self):
        with patch.object(redis_cache, "flush_metrics", return_value={"hc": 5}) as m:
            assert cache_service.flush_metrics() == {"hc": 5}


# ═════════════════════════════════════════════════════════════════════════════
# Centralized invalidation
# ═════════════════════════════════════════════════════════════════════════════


class TestDocumentCacheInvalidation:
    def test_invalidates_correct_key(self):
        uid = uuid.uuid4()
        with patch("app.services.cache_service.cache_service.delete") as m:
            invalidate_document_cache(uid)
        m.assert_called_once_with(document_list_key(uid))

    def test_noop_on_redis_unavailable(self):
        with patch("app.services.cache_service.cache_service.delete", return_value=False):
            invalidate_document_cache(uuid.uuid4())  # must not raise


class TestMemoryCacheInvalidation:
    def test_with_type_uses_delete_single_key(self):
        uid = uuid.uuid4()
        with patch("app.services.cache_service.cache_service.delete") as m:
            invalidate_memory_cache(uid, memory_type=MemoryType.FACT)
        m.assert_called_once_with(memory_list_key(uid, MemoryType.FACT))

    def test_without_type_uses_delete_pattern(self):
        uid = uuid.uuid4()
        with patch("app.services.cache_service.cache_service.delete_pattern") as m:
            invalidate_memory_cache(uid)
        m.assert_called_once_with(f"memories:{uid}:*")


class TestConversationCacheInvalidation:
    def test_invalidates_correct_key(self):
        uid = uuid.uuid4()
        with patch("app.services.cache_service.cache_service.delete") as m:
            invalidate_conversation_cache(uid)
        m.assert_called_once_with(conversation_list_key(uid))


class TestMessageCacheInvalidation:
    def test_invalidates_pattern(self):
        cid = uuid.uuid4()
        with patch("app.services.cache_service.cache_service.delete_pattern") as m:
            invalidate_message_cache(cid)
        m.assert_called_once_with(f"messages:{cid}:*")


class TestSearchCacheInvalidation:
    def test_invalidates_pattern(self):
        uid = uuid.uuid4()
        with patch("app.services.cache_service.cache_service.delete_pattern") as m:
            invalidate_search_cache(uid)
        m.assert_called_once_with(f"search:{uid}:*")


# ═════════════════════════════════════════════════════════════════════════════
# Full round-trips
# ═════════════════════════════════════════════════════════════════════════════


class TestCacheRoundTrip:
    """Full get / set / delete round trips with a live mock Redis."""

    def test_set_and_get(self):
        mc = _make_mock_client()
        mc.get.return_value = json.dumps({"msg": "hello"})
        with _patch_redis(mc):
            assert redis_cache.set("rt:key", {"msg": "hello"}, ttl=60)
            result = redis_cache.get("rt:key")
        assert result == {"msg": "hello"}

    def test_set_overwrites_existing(self):
        mc = _make_mock_client()
        with _patch_redis(mc):
            redis_cache.set("k", "v1")
            redis_cache.set("k", "v2")
        assert mc.setex.call_count == 2

    def test_delete_existing_key_then_get_returns_none(self):
        mc = _make_mock_client()
        mc.get.return_value = None
        with _patch_redis(mc):
            redis_cache.delete("k")
            result = redis_cache.get("k")
        assert result is None

    def test_exists_after_delete_returns_false(self):
        mc = _make_mock_client()
        mc.exists.return_value = 0
        with _patch_redis(mc):
            redis_cache.delete("k")
            assert redis_cache.exists("k") is False
