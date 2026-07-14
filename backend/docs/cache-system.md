# Cache System

## Architecture

The cache layer sits between the service layer and a Redis 8.0+ instance. It
implements the **cache-aside** pattern: every read checks the cache first; on a
miss the service fetches from the primary store (PostgreSQL / Qdrant) and writes
the result into the cache with a TTL. Writes invalidate the relevant cache keys
so subsequent reads see fresh data.

```
┌──────────────────┐     ┌───────────────────┐     ┌────────────────┐
│   API Endpoint   │ ──▶ │   Service Layer    │ ──▶ │  PostgreSQL /  │
│  (FastAPI route) │     │  (cache-aside)     │     │    Qdrant      │
└──────────────────┘     └───────┬───────────┘     └────────────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │   RedisCache      │
                        │  (app/core/cache) │
                        └────────┬─────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │   Redis 8.0+     │
                        │  (in-memory KV)  │
                        └──────────────────┘
```

Three modules form the cache layer:

| Module | Responsibility |
|---|---|
| `app/core/cache.py` | Raw Redis operations — connection pooling, lazy init, graceful degradation, metrics counters. |
| `app/core/cache_keys.py` | Key generation helpers — every cache key is produced by a named function so key schemas are documented in one place. |
| `app/services/cache_service.py` | JSON serialization layer on top of `RedisCache`, plus centralized invalidation functions consumed by services. |

Services interact **only** with `cache_service`; they never import `RedisCache`
directly. Invalidation functions use `delete` for a single key and
`delete_pattern` (via Redis `SCAN`) for bulk invalidation.

---

## Cache-Aside Pattern

Every cached read follows the same flow:

```
1. Generate cache key via app/core/cache_keys helper
2. cache_service.get(key)
3. If HIT → deserialize JSON, return immediately
4. If MISS → query primary store (DB / Qdrant)
5. cache_service.set(key, result, ttl=...)
6. Return result
```

Every write that could stale cached data calls the appropriate invalidation
function *after* the database write succeeds:

```
1. Perform DB write (create / update / delete)
2. invalidate_xxx_cache(...) → cache_service.delete / delete_pattern
```

Because cache is never a correctness dependency, a Redis outage only affects
latency — every operation degrades to a full primary-store read.

---

## Redis Lifecycle

### Startup

The `RedisCache` singleton uses **lazy initialization**: no Redis connection is
created at import time. The first operation that accesses `_client` triggers
`_get_client()`:

1. Check `settings.CACHE_ENABLED` — if `False`, skip entirely.
2. Call `redis.from_url(settings.REDIS_URL)` with connection pooling.
3. Call `client.ping()` to verify the connection.
4. On success: log and store the client. On failure: log a warning, set
   `_client = None`, and return safe defaults for all subsequent operations.

### Connection Pooling

```
redis.connection.ConnectionPool(
    max_connections=10,
    retry_on_timeout=True,
    socket_keepalive=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)
```

Pool is created once by `redis.from_url()`. Connections are reused across
requests and released back to the pool after each call.

### Shutdown

A `close()` method exists to tear down the connection pool. It is called
automatically by FastAPI's `lifespan` shutdown handler and during test cleanup.

---

## Cache Keys

Every key is produced by a named function in `app/core/cache_keys.py`.

### Key Schema

| Cache | Key Pattern | Function |
|---|---|---|
| Document list | `docs:{user_id}` | `document_list_key(user_id)` |
| Memory list | `memories:{user_id}:{memory_type}:{is_active}` | `memory_list_key(user_id, memory_type, is_active)` |
| Conversation list | `conversations:{user_id}` | `conversation_list_key(user_id)` |
| Messages (paginated) | `messages:{conversation_id}:{page}:{page_size}` | `conversation_messages_key(conversation_id, page, page_size)` |
| Search (Qdrant) | `search:{user_id}:{md5(query)}` | `search_key(user_id, query)` |

### Design Principles

1. **User-scoped** — every key includes `user_id` (or `conversation_id` which is
   itself user-scoped). This guarantees cross-user isolation: one user's cache
   data can never be served to another user.
2. **Deterministic** — `search_key` incorporates an MD5 hash of the query so the
   same query from the same user always produces the same key.
3. **Scannable** — patterns like `memories:{user_id}:*` and `messages:{cid}:*`
   allow bulk invalidation via `SCAN` + `DELETE`.

---

## TTL Strategy

| Cache | TTL | Config Key |
|---|---|---|
| Document list | 120 s (2 min) | `CACHE_DOCUMENT_TTL` |
| Memory list | 600 s (10 min) | `CACHE_MEMORY_TTL` |
| Conversation list | 120 s (2 min) | `CACHE_CONVERSATION_TTL` |
| Messages | 120 s (2 min) | `CACHE_MESSAGE_TTL` |
| Search (Qdrant) | 300 s (5 min) | `CACHE_SEARCH_TTL` |
| Fallback default | 300 s (5 min) | `CACHE_DEFAULT_TTL` |

### Rationale

- **Search results** are relatively expensive (vector + LLM) so they get a
  moderate 5-minute TTL.
- **Document / Conversation / Message** lists are cheap to query but change
  frequently; 2 minutes balances freshness with latency savings.
- **Memories** change less often and are accessed across many requests; 10
  minutes reduces DB load without sacrificing freshness.
- All TTLs are configurable via environment variables in `Settings`.

---

## Invalidation Strategy

Invalidation uses a **write-through** approach: every mutating endpoint calls
the relevant invalidation function after its DB write completes.

### Invalidation Functions

| Function | Scope | Mechanism |
|---|---|---|
| `invalidate_document_cache(user_id)` | Document list for user | `DELETE docs:{user_id}` |
| `invalidate_memory_cache(user_id, memory_type=None)` | Memory list for user | `DELETE memories:{user_id}:{type}:{active}` (with type) or `SCAN memories:{user_id}:*` + `DELETE` (without type) |
| `invalidate_conversation_cache(user_id)` | Conversation list for user | `DELETE conversations:{user_id}` |
| `invalidate_message_cache(conversation_id)` | All message pages for conversation | `SCAN messages:{cid}:*` + `DELETE` |
| `invalidate_search_cache(user_id)` | All search results for user | `SCAN search:{uid}:*` + `DELETE` |

### When Invalidation Is Called

| Endpoint | Invalidation |
|---|---|
| Upload document | `invalidate_document_cache` + `invalidate_search_cache` |
| Delete document | `invalidate_document_cache` + `invalidate_search_cache` |
| Create memory | `invalidate_memory_cache` |
| Update memory | `invalidate_memory_cache` |
| Delete memory | `invalidate_memory_cache` |
| Create conversation | `invalidate_conversation_cache` |
| Update conversation title | `invalidate_conversation_cache` |
| Delete conversation | `invalidate_conversation_cache` |
| Save message | `invalidate_message_cache` |
| Update message status | `invalidate_message_cache` |

### Why Not TTL-Only?

TTL alone would serve stale data until expiry. Invalidation ensures that after a
write, the next read is guaranteed to hit the primary store regardless of the
TTL. TTL is the safety net — it prevents stale data from living forever if
invalidation is somehow missed.

---

## Serialization

All cache values are serialized to JSON via Python's `json.dumps` / `json.loads`
with custom encoders:

| Python Type | JSON Representation |
|---|---|
| `uuid.UUID` | `str(uuid)` — e.g. `"550e8400-e29b-..."` |
| `datetime` (aware) | ISO 8601 — e.g. `"2026-07-10T12:00:00+00:00"` |
| `datetime` (naive) | ISO 8601 without tz — e.g. `"2026-07-10T12:00:00"` |
| `None` | `null` |
| `list` / `dict` | Recursively serialized |
| `str` / `int` / `float` / `bool` | Native JSON |

The custom `CacheEncoder` class in `cache_service.py` handles UUID and datetime
conversion. Deserialization never raises — malformed JSON causes a cache miss
(none returned) rather than an error propagating to the caller.

---

## Graceful Degradation

Redis is **never a hard dependency**. Every `RedisCache` method catches
exceptions and returns a safe default:

| Operation | Safe Default on Error |
|---|---|
| `get(key)` | `None` (cache miss) |
| `set(key, value, ttl)` | `False` |
| `delete(key)` | `False` |
| `delete_pattern(pattern)` | `0` |
| `exists(key)` | `False` |
| `ttl(key)` | `-2` (Redis convention for missing key) |

### Degradation Modes

1. **Cache disabled** — `settings.CACHE_ENABLED = False`. Operations return
   safe defaults immediately without any network call.
2. **Redis unreachable** — `ping()` or any operation raises
   `redis.exceptions.ConnectionError`, `TimeoutError`, or `OSError`. The client
   is set to `None`, a warning is logged once, and all subsequent operations
   return safe defaults until the process restarts (no reconnection loop).
3. **Transient failure** — A single operation fails but subsequent calls
   reconnect via the connection pool.

When Redis recovers after a full disconnect, the application must be restarted
to re-establish the connection. This is intentional — it avoids silent partial
failures and makes the operator aware of the outage via logs.

---

## Metrics

`RedisCache` maintains two counters:

- `hit_count` — number of `get()` calls that returned a non-None value.
- `miss_count` — number of `get()` calls that returned None.

Derived properties:

- `hit_rate` — `hit_count / (hit_count + miss_count)` (0.0 if no operations).
- `flush_metrics()` — returns `{"hit_count", "miss_count", "hit_rate", ...}` and
  resets the counters to zero. Called by the `/health` endpoint and monitoring
  scrapers.

Metrics are process-local and reset on restart. They are **not** persisted to
Redis.

---

## Configuration

All caching configuration lives in `app/core/config.py` under the `Settings`
class. Set via environment variables or `.env` file.

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://` | Redis connection string. Set to empty to disable. |
| `CACHE_ENABLED` | `True` | Master switch. When `False`, no Redis connection is attempted. |
| `CACHE_DEFAULT_TTL` | `300` | Fallback TTL in seconds when no specific TTL is provided. |
| `CACHE_SEARCH_TTL` | `300` | TTL for Qdrant search results (seconds). |
| `CACHE_DOCUMENT_TTL` | `120` | TTL for document list cache (seconds). |
| `CACHE_MEMORY_TTL` | `600` | TTL for memory list cache (seconds). |
| `CACHE_CONVERSATION_TTL` | `120` | TTL for conversation list cache (seconds). |
| `CACHE_MESSAGE_TTL` | `120` | TTL for message list cache (seconds). |

---

## Integration Points

Services that use the cache layer:

| Service | File | Cached Operations |
|---|---|---|
| `file_service.py` | `list_documents()` | Document list |
| `memory_service.py` | `list_memories()` | Memory list |
| `conversation_service.py` | `list_conversations()` | Conversation list |
| `message_service.py` | `get_messages()` | Paginated messages |
| `rag_service.py` | `answer_question()`, `stream_answer()` | Qdrant search results (before LLM call) |

Integration follows the same pattern in every service:

```python
# Cache-aside read
key = some_list_key(user_id)
cached = cache_service.get(key)
if cached is not None:
    return [SomeSchema(**item) for item in cached]

# Cache miss — query DB
results = db.query(...).all()
cache_service.set(key, [r.to_dict() for r in results], ttl=settings.CACHE_SOME_TTL)
return results

# Invalidation on write
invalidate_some_cache(user_id)
```

---

## Security Considerations

1. **No sensitive data in cache.** Cache values may include document metadata
   (titles, types, timestamps) but never document content, message bodies, or
   LLM responses. Authentication tokens, passwords, and API keys are never
   cached.
2. **User isolation by key prefix.** Every key includes `user_id` so there is no
   way for one user's data to collide with another's. The `search_key` function
   hashes the query with MD5 — this is a key-consistency hash, not a security
   mechanism.
3. **Redis URL from environment only.** The `REDIS_URL` credential is read from
   `settings` (which loads from `.env` / environment variables). It is never
   hardcoded, logged, or exposed in error messages.
4. **No Redis ACL/encryption in app.** Redis authentication (AUTH), TLS, and ACL
   are handled at the infrastructure layer via the `REDIS_URL` scheme
   (`rediss://` for TLS). The application does not manage Redis credentials.

---

## Future Improvements

- **Prometheus metrics** — export `hit_count`, `miss_count`, `hit_rate` as
  Prometheus gauge/counter metrics instead of process-local counters.
- **Key-level compression** — compress values over a threshold (e.g., 1 KB) with
  `zlib` before storing, decompress on read.
- **Distributed tracing** — add OpenTelemetry spans around every cache operation
  for latency breakdown.
- **Circuit breaker** — instead of permanently disabling the client on first
  failure, implement a circuit breaker that retries after a cooldown.
- **Read-through / write-through** — promote from cache-aside to read-through
  (Redis handles DB fetch transparently) or write-through (Redis is updated
  synchronously with DB) for stronger consistency guarantees.
- **Local L1 cache** — add an in-process LRU cache (e.g., `cachetools.TTLCache`)
  in front of Redis for the hottest keys to reduce network round-trips.
- **Cache warming** — pre-populate common keys on application startup.
