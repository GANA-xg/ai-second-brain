# Vector Database — Qdrant Integration

## Architecture Overview

The AI Second Brain uses [Qdrant](https://qdrant.tech/) as its vector database for
semantic search. The integration follows a single-collection, multi-tenant design
with strict user isolation enforced at the query level.

```
┌──────────────┐       ┌───────────────────┐       ┌─────────────────┐
│  Embedding    │──────▶│  QdrantService    │──────▶│   Qdrant (HTTP) │
│  Pipeline     │       │  (Service Layer)  │       │  Vector Store   │
└──────────────┘       └───────────────────┘       └─────────────────┘
                               │
                               ▼
                        ┌───────────────────┐
                        │  Health Endpoint  │
                        │  (Status Check)   │
                        └───────────────────┘
```

### Integration Points

| Layer | Component | Role |
|-------|-----------|------|
| **Config** | `Settings` | Qdrant URL, API key, timeout, retries |
| **Service** | `QdrantService` | Collection lifecycle, upsert, search, delete |
| **Pipeline** | `EmbeddingPipeline.process()` | Phase 6: Qdrant upsert after DB persist |
| **File Service** | `FileService.delete_document()` | Cascade delete from Qdrant before DB soft-delete |
| **Health** | `HealthService.get_health()` | Aggregates Qdrant status into health endpoint |

---

## Collection Schema

### Single Collection: `chunk_embeddings` (configurable)

**Collection Parameters:**
- **Dimension:** `VECTOR_DIMENSION` (default: `384` — all-MiniLM-L6-v2)
- **Distance:** `Cosine` (cosine similarity)
- **Name:** `QDRANT_COLLECTION` config key (default: `"chunk_embeddings"`)

### Payload Schema

Every vector point carries the following payload fields for filtering and metadata:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | `str` (UUID) | ✅ | Tenant identifier — **required on every query** |
| `document_id` | `str` (UUID) | ✅ | Parent document identifier |
| `chunk_id` | `str` (UUID) | ✅ | Chunk identifier (uniqueness per embedding version) |
| `embedding_version` | `str` | ✅ | Model version tag (e.g. `"v1"`) |
| `embedding_model` | `str` | ✅ | Full model name (e.g. `sentence-transformers/all-MiniLM-L6-v2`) |
| `chunk_index` | `int` | ❌ | Position within the document |
| `source_type` | `str` | ❌ | File extension / document type |
| `page_number` | `int` | ❌ | Page number (PDF documents) |
| `slide_number` | `int` | ❌ | Slide number (presentation documents) |
| `section` | `str` | ❌ | Section header (markdown/chapter-based documents) |
| `created_at` | `str` (ISO 8601) | ❌ | Embedding creation timestamp |

### Payload Indexes

The following fields are indexed in Qdrant for efficient filtering:

- `user_id` — Keyword index
- `document_id` — Keyword index
- `chunk_id` — Keyword index

---

## Filtering Strategy

### Mandatory User-Isolation Filter

Every search and delete operation requires `user_id` as a keyword-only argument.
Internally, the `query_filter` always includes:

```
must = [
    Filter(key="user_id", match=MatchValue(value=str(user_id)))
]
```

This enforces **server-side filtering** — Qdrant retrieves only vectors belonging
to the authenticated user. The `user_id` filter cannot be omitted; there is no
unfiltered code path in the application.

### Optional Filters

- **document_ids (list[str])** — restricts search to specific documents
  (added as an additional `must` condition)
- **Limit (int)** — controls the number of results returned (default: `10`)

---

## Security Model

1. **No unfiltered search:** `QdrantService.search()` requires `user_id` as a
   keyword-only argument. The `query_filter` is always constructed with
   `user_id` in the `must` clause.
2. **Cascade delete:** When a document is deleted (soft-delete in PostgreSQL),
   `file_service.delete_document()` calls
   `vector_service.delete_by_document()` **before** the DB delete, ensuring
   no stale vectors remain.
3. **Payload transparency:** Search returns payload fields only (with_payload=True)
   and never returns raw vectors (with_vectors=False), reducing data exposure.
4. **No content in logs:** Embeddings, chunk text, and document contents are
   never written to structured logs. Only metadata (count, user_id, document_id,
   collection name, latency) is logged.

---

## Vector Lifecycle

### Upsert Path

```
Document Upload
        │
        ▼
Chunking (Phase 3)
        │
        ▼
Embedding Generation (Phase 4)
        │
        ▼
DB Persist → ChunkEmbedding table (Phase 5)
        │
        ▼
Qdrant Upsert (Phase 6)
   • deterministic point ID = uuid.uuid5(
        uuid.NAMESPACE_DNS,
           f"{document_id}:{chunk_id}"
        )     
   • upsert is naturally idempotent (deterministic point ID overwrites)
   • payload includes user_id, document_id, chunk_id + metadata
```

### Delete Path (Cascade)

```
Delete Document Request
        │
        ▼
Vector DB delete (by user_id + document_id)
        │
        ▼
PostgreSQL soft-delete
```

### Chunk Delete

```
Delete Chunk
        │
        ▼
Vector DB delete (by user_id + document_id + chunk_id)
```

---

## Configuration Reference

All Qdrant settings live in `backend/app/core/config.py` under `Settings`:

| Setting | Default | Description |
|---------|---------|-------------|
| `QDRANT_URL` | `"http://localhost:6333"` | Qdrant server URL |
| `QDRANT_API_KEY` | `None` | API key for authenticated Qdrant |
| `QDRANT_COLLECTION` | `"chunk_embeddings"` | Collection name |
| `VECTOR_DIMENSION` | `384` | Embedding dimension (all-MiniLM-L6-v2) |
| `VECTOR_DISTANCE` | `"Cosine"` | Distance metric |
| `QDRANT_TIMEOUT_SECONDS` | `30` | Client connection timeout |
| `QDRANT_MAX_RETRIES` | `3` | Retry count for transient failures |

---

## Operational Notes

### Retry Behaviour

Qdrant operations use a simple retry loop with incremental backoff:

- **Max attempts:** `QDRANT_MAX_RETRIES` (default: 3)
- **Wait:** `0.5 × attempt_number` seconds between retries
- **Retry:** All exceptions caught by the retry loop; after exhaustion a `VectorServiceError` is raised with the failed operation name and retry count.

Transient failures (ConnectionError, timeouts) trigger up to 3 attempts with
backoff (0.5s, 1.0s). After exhaustion, a `VectorServiceError`
is raised with the failed operation name and retry count.

### Health Check

`qdrantservice.health_check()` returns:

```json
{
    "status": "healthy",
    "collection_exists": true,
    "latency_ms": 1.23
}
```

On failure:

```json
{
    "status": "unhealthy",
    "collection_exists": false,
    "error": "Connection refused"
}
```

The health endpoint (`GET /api/v1/health`) aggregates Qdrant status alongside
database and other dependency checks.

### Singleton Pattern

`get_vector_service()` returns a lazily-initialized singleton. The QdrantClient
is created on first access (not on import), preventing connection attempts
during import cycles. `close()` releases the client; the next access re-creates it.

### Idempotency

- **Collection creation:** `ensure_collection()` checks existence first via
  `client.get_collection()`. If it exists, no creation happens.
- **Vector upsert:** Uses deterministic point IDs so repeated upserts with
  the same data are safe (natural delete-then-insert).
- **Delete:** Deleting a non-existent document or collection does not raise.

### Running Qdrant Locally

```bash
# Using Docker
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant

# Or via docker-compose
docker compose up -d qdrant
```

See `docker-compose.yml` in the project root for the full stack definition.
