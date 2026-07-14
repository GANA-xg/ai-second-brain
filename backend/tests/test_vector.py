"""Tests for the Qdrant vector database service (Part 7).

Tests cover:
  - Collection management (creation, repeated init, deletion)
  - Vector upsert (single, batch, idempotency, payload metadata)
  - Vector search (user isolation, document filtering, top-k ordering)
  - Security filtering (User A cannot retrieve User B vectors)
  - Delete operations (by document, by chunk, repeated)
  - Failure handling (retry, timeout, exhaustion)
  - Structured logging (events emitted, no content leakage)
  - Health check

All tests use mocked QdrantClient since no local Qdrant instance is required.
"""

import logging
import uuid
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.core.config import settings
from app.services.vector_service import (
    VectorService,
    VectorServiceError,
    get_vector_service,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_USER_ID = uuid.uuid4()
TEST_USER_ID_ALT = uuid.uuid4()
TEST_DOCUMENT_ID = uuid.uuid4()
TEST_DIMENSION = settings.VECTOR_DIMENSION


def _random_vector(dim: int = TEST_DIMENSION) -> list[float]:
    """Generate a random unit-normalized embedding vector."""
    v = np.random.default_rng(42).uniform(-0.1, 0.1, dim).astype(np.float32)
    v = v / np.linalg.norm(v)
    return v.tolist()


def _make_vector_dict(chunk_id=None, overrides=None):
    """Build a standard vector dict for upsert testing."""
    v = {
        "chunk_id": chunk_id or uuid.uuid4(),
        "vector": _random_vector(),
        "payload": {
            "chunk_index": 0,
            "embedding_version": "v1",
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "source_type": "txt",
            "page_number": None,
            "slide_number": None,
            "section": None,
            "created_at": "2026-07-08T00:00:00+00:00",
        },
    }
    if overrides:
        v.update(overrides)
    return v


def _make_qdrant_hit(chunk_id, user_id, document_id, score=0.85, **extra):
    """Create a mock Qdrant ScoredPoint."""
    from qdrant_client.http import models as qmodels

    payload = {
        "user_id": user_id,
        "document_id": document_id,
        "chunk_id": chunk_id,
        "embedding_version": "v1",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        **extra,
    }
    hit = MagicMock(spec=qmodels.ScoredPoint)
    hit.id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}:{chunk_id}"))
    hit.score = score
    hit.payload = payload
    hit.version = 0
    return hit


def _make_query_response(points):
    """Wrap a list of ScoredPoints into a query_points response."""
    qr = MagicMock()
    qr.points = points
    return qr


def _raise_not_found(*args, **kwargs):
    """Helper to raise UnexpectedResponse with 404 status."""
    from qdrant_client.http.exceptions import UnexpectedResponse

    raise UnexpectedResponse(
        status_code=404,
        reason_phrase="Not Found",
        headers={},
        content=b'{"status":{"error":"Not found"}}',
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the global vector service singleton before and after each test."""
    import app.services.vector_service as vs_mod

    vs_mod._vector_service = None
    yield
    vs_mod._vector_service = None


@pytest.fixture
def mock_qdrant_client():
    """Create a fully-mocked QdrantClient."""
    with patch("app.services.vector_service.QdrantClient") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def vector_service(mock_qdrant_client):
    """Return a VectorService instance with mocked client."""
    vs = VectorService()
    _ = vs.client  # trigger lazy init
    return vs


# ===================================================================
# Collection Management
# ===================================================================


class TestVectorCollection:
    """Collection creation and lifecycle."""

    def test_ensure_collection_creates_when_missing(self, vector_service, mock_qdrant_client):
        """First call should create the collection when it doesn't exist."""
        mock_qdrant_client.get_collection.side_effect = _raise_not_found

        vector_service.ensure_collection()

        mock_qdrant_client.create_collection.assert_called_once()
        call_kwargs = mock_qdrant_client.create_collection.call_args[1]
        assert call_kwargs["collection_name"] == settings.QDRANT_COLLECTION
        assert call_kwargs["vectors_config"].size == settings.VECTOR_DIMENSION

    def test_ensure_collection_skips_when_exists(self, vector_service, mock_qdrant_client):
        """If collection already exists, no creation call."""
        mock_qdrant_client.get_collection.return_value = MagicMock()

        vector_service.ensure_collection()

        mock_qdrant_client.create_collection.assert_not_called()

    def test_ensure_collection_idempotent_repeated(self, vector_service, mock_qdrant_client):
        """Calling ensure_collection multiple times is safe."""
        mock_qdrant_client.get_collection.return_value = MagicMock()

        vector_service.ensure_collection()
        vector_service.ensure_collection()
        vector_service.ensure_collection()

        mock_qdrant_client.get_collection.assert_called()
        mock_qdrant_client.create_collection.assert_not_called()

    def test_delete_collection(self, vector_service, mock_qdrant_client):
        """Delete collection calls through to Qdrant."""
        vector_service.delete_collection()
        mock_qdrant_client.delete_collection.assert_called_once_with(
            settings.QDRANT_COLLECTION
        )

    def test_delete_collection_not_found(self, vector_service, mock_qdrant_client):
        """Deleting a non-existent collection should not raise."""
        from qdrant_client.http.exceptions import UnexpectedResponse

        mock_qdrant_client.delete_collection.side_effect = UnexpectedResponse(
            status_code=404,
            reason_phrase="Not Found",
            headers={},
            content=b'{}',
        )
        # Should not raise
        vector_service.delete_collection()

    def test_collection_creates_payload_indexes(self, vector_service, mock_qdrant_client):
        """After creation, payload indexes are created for filter fields."""
        mock_qdrant_client.get_collection.side_effect = _raise_not_found

        vector_service.ensure_collection()

        # Should have created indexes for user_id, document_id, chunk_id
        index_calls = mock_qdrant_client.create_payload_index.call_args_list
        indexed_fields = [c[1]["field_name"] for c in index_calls]
        assert "user_id" in indexed_fields
        assert "document_id" in indexed_fields
        assert "chunk_id" in indexed_fields


# ===================================================================
# Vector Upsert
# ===================================================================


class TestVectorUpsert:
    """Upsert operations."""

    def test_upsert_single_vector(self, vector_service, mock_qdrant_client):
        """Single vector upsert succeeds."""
        vectors = [_make_vector_dict(chunk_id=uuid.uuid4())]

        result = vector_service.upsert_vectors(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            vectors=vectors,
        )

        assert result["upserted_count"] == 1
        assert result["latency_ms"] >= 0
        mock_qdrant_client.upsert.assert_called_once()

    def test_upsert_batch_vectors(self, vector_service, mock_qdrant_client):
        """Batch upsert with multiple vectors."""
        vectors = [_make_vector_dict(chunk_id=uuid.uuid4()) for _ in range(10)]

        result = vector_service.upsert_vectors(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            vectors=vectors,
        )

        assert result["upserted_count"] == 10
        call_args = mock_qdrant_client.upsert.call_args[1]
        assert len(call_args["points"]) == 10

    def test_upsert_empty_returns_zero(self, vector_service, mock_qdrant_client):
        """Empty vector list returns immediately without API call."""
        result = vector_service.upsert_vectors(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            vectors=[],
        )

        assert result["upserted_count"] == 0
        mock_qdrant_client.upsert.assert_not_called()

    def test_upsert_builds_payload(self, vector_service, mock_qdrant_client):
        """Each point has the correct payload structure."""
        chunk_id = uuid.uuid4()
        vectors = [_make_vector_dict(chunk_id=chunk_id)]

        vector_service.upsert_vectors(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            vectors=vectors,
        )

        call_args = mock_qdrant_client.upsert.call_args[1]
        point = call_args["points"][0]
        payload = point.payload

        # Required fields
        assert payload["user_id"] == str(TEST_USER_ID)
        assert payload["document_id"] == str(TEST_DOCUMENT_ID)
        assert payload["chunk_id"] == str(chunk_id)
        # Additional payload metadata
        assert payload["chunk_index"] == 0
        assert payload["embedding_version"] == "v1"
        assert payload["source_type"] == "txt"

    def test_upsert_deterministic_point_id(self, vector_service, mock_qdrant_client):
        """Same document+chunk produces the same point ID (deterministic)."""
        chunk_id = uuid.uuid4()
        vectors = [_make_vector_dict(chunk_id=chunk_id)]

        # First call
        vector_service.upsert_vectors(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            vectors=vectors,
        )
        first_point_id = mock_qdrant_client.upsert.call_args[1]["points"][0].id

        mock_qdrant_client.reset_mock()

        # Second call with same IDs
        vector_service.upsert_vectors(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            vectors=vectors,
        )
        second_point_id = mock_qdrant_client.upsert.call_args[1]["points"][0].id

        assert first_point_id == second_point_id


# ===================================================================
# Vector Search
# ===================================================================


class TestVectorSearch:
    """Search operations with mandatory user filtering."""

    def test_search_with_user_filter(self, vector_service, mock_qdrant_client):
        """Search always includes user_id filter in the query."""
        mock_qdrant_client.query_points.return_value = _make_query_response([
            _make_qdrant_hit(
                chunk_id=str(uuid.uuid4()),
                user_id=str(TEST_USER_ID),
                document_id=str(TEST_DOCUMENT_ID),
            )
        ])

        results = vector_service.search(
            user_id=TEST_USER_ID,
            query_vector=_random_vector(),
            limit=5,
        )

        assert len(results) == 1
        # Verify filter was included
        filter_args = mock_qdrant_client.query_points.call_args[1]
        assert "query_filter" in filter_args
        filter_ = filter_args["query_filter"]
        assert filter_ is not None
        conditions = filter_.must
        user_condition = conditions[0]
        assert user_condition.key == "user_id"
        assert user_condition.match.value == str(TEST_USER_ID)

    def test_search_with_document_filter(self, vector_service, mock_qdrant_client):
        """Search with document_ids restricts to those documents."""
        doc_ids = [uuid.uuid4(), uuid.uuid4()]
        mock_qdrant_client.query_points.return_value = _make_query_response([])

        vector_service.search(
            user_id=TEST_USER_ID,
            query_vector=_random_vector(),
            document_ids=doc_ids,
        )

        filter_args = mock_qdrant_client.query_points.call_args[1]
        filter_ = filter_args["query_filter"]
        conditions = filter_.must
        assert len(conditions) == 2
        assert conditions[0].key == "user_id"
        assert conditions[1].key == "document_id"

    def test_search_top_k_ordering(self, vector_service, mock_qdrant_client):
        """Results are ordered by descending score."""
        mock_qdrant_client.query_points.return_value = _make_query_response([
            _make_qdrant_hit(str(uuid.uuid4()), str(TEST_USER_ID), str(TEST_DOCUMENT_ID), score=0.95),
            _make_qdrant_hit(str(uuid.uuid4()), str(TEST_USER_ID), str(TEST_DOCUMENT_ID), score=0.80),
            _make_qdrant_hit(str(uuid.uuid4()), str(TEST_USER_ID), str(TEST_DOCUMENT_ID), score=0.65),
        ])

        results = vector_service.search(
            user_id=TEST_USER_ID,
            query_vector=_random_vector(),
            limit=3,
        )

        assert len(results) == 3
        assert results[0]["score"] >= results[1]["score"]
        assert results[1]["score"] >= results[2]["score"]

    def test_search_respects_limit(self, vector_service, mock_qdrant_client):
        """The limit parameter is passed to Qdrant."""
        mock_qdrant_client.query_points.return_value = _make_query_response([])

        vector_service.search(
            user_id=TEST_USER_ID,
            query_vector=_random_vector(),
            limit=7,
        )

        call_args = mock_qdrant_client.query_points.call_args[1]
        assert call_args["limit"] == 7

    def test_search_empty_results(self, vector_service, mock_qdrant_client):
        """Search with no matching results returns empty list."""
        mock_qdrant_client.query_points.return_value = _make_query_response([])

        results = vector_service.search(
            user_id=TEST_USER_ID,
            query_vector=_random_vector(),
        )

        assert results == []

    def test_search_invalid_collection_raises(self, vector_service, mock_qdrant_client):
        """Search on non-existent collection raises appropriate error."""
        mock_qdrant_client.query_points.side_effect = _raise_not_found

        with pytest.raises(VectorServiceError):
            vector_service.search(
                user_id=TEST_USER_ID,
                query_vector=_random_vector(),
            )

    def test_search_with_vectors_false(self, vector_service, mock_qdrant_client):
        """Search does not return raw vectors (only payload)."""
        mock_qdrant_client.query_points.return_value = _make_query_response([
            _make_qdrant_hit(str(uuid.uuid4()), str(TEST_USER_ID), str(TEST_DOCUMENT_ID)),
        ])

        vector_service.search(
            user_id=TEST_USER_ID,
            query_vector=_random_vector(),
        )

        call_args = mock_qdrant_client.query_points.call_args[1]
        assert call_args["with_vectors"] is False
        assert call_args["with_payload"] is True


# ===================================================================
# Security — User Isolation
# ===================================================================


class TestVectorFiltering:
    """Tests ensuring user-level isolation is enforced."""

    def test_user_isolation_enforced(self, vector_service, mock_qdrant_client):
        """User A's search won't return User B's vectors."""
        mock_qdrant_client.query_points.return_value = _make_query_response([
            _make_qdrant_hit(
                chunk_id=str(uuid.uuid4()),
                user_id=str(TEST_USER_ID),
                document_id=str(TEST_DOCUMENT_ID),
            ),
        ])

        results = vector_service.search(
            user_id=TEST_USER_ID,
            query_vector=_random_vector(),
        )

        # Verify the user_id filter was passed to Qdrant
        filter_args = mock_qdrant_client.query_points.call_args[1]
        filter_ = filter_args["query_filter"]
        conditions = filter_.must
        user_conds = [c for c in conditions if c.key == "user_id"]
        assert len(user_conds) == 1
        assert user_conds[0].match.value == str(TEST_USER_ID)

        # Verify no cross-user results
        for r in results:
            assert r["payload"]["user_id"] == str(TEST_USER_ID)

    def test_search_always_has_user_filter(self, vector_service, mock_qdrant_client):
        """Every search call always includes user_id — no unfiltered code path."""
        mock_qdrant_client.query_points.return_value = _make_query_response([])

        vector_service.search(
            user_id=TEST_USER_ID,
            query_vector=_random_vector(),
        )

        filter_args = mock_qdrant_client.query_points.call_args[1]
        filter_ = filter_args["query_filter"]
        assert filter_ is not None
        assert any(c.key == "user_id" for c in filter_.must)

    def test_delete_by_document_user_scoped(self, vector_service, mock_qdrant_client):
        """delete_by_document includes both user_id and document_id filter."""
        vector_service.delete_by_document(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
        )

        filter_arg = mock_qdrant_client.delete.call_args[1]
        selector = filter_arg["points_selector"]
        filter_ = selector.filter
        keys = {c.key for c in filter_.must}
        assert "user_id" in keys
        assert "document_id" in keys

    def test_delete_by_chunk_user_scoped(self, vector_service, mock_qdrant_client):
        """delete_by_chunk includes user_id, document_id, AND chunk_id filter."""
        vector_service.delete_by_chunk(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            chunk_id=uuid.uuid4(),
        )

        filter_arg = mock_qdrant_client.delete.call_args[1]
        selector = filter_arg["points_selector"]
        filter_ = selector.filter
        keys = {c.key for c in filter_.must}
        assert "user_id" in keys
        assert "document_id" in keys
        assert "chunk_id" in keys


# ===================================================================
# Delete Operations
# ===================================================================


class TestVectorDelete:
    """Vector deletion operations."""

    def test_delete_by_document(self, vector_service, mock_qdrant_client):
        """Delete all vectors for a document succeeds."""
        result = vector_service.delete_by_document(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
        )

        assert result["deleted"] is True
        mock_qdrant_client.delete.assert_called_once()

    def test_delete_by_chunk(self, vector_service, mock_qdrant_client):
        """Delete a single chunk's vector."""
        result = vector_service.delete_by_chunk(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            chunk_id=uuid.uuid4(),
        )

        assert result["deleted"] is True
        mock_qdrant_client.delete.assert_called_once()

    def test_repeated_delete_safe(self, vector_service, mock_qdrant_client):
        """Deleting an already-deleted document doesn't error."""
        result = vector_service.delete_by_document(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
        )
        assert result["deleted"] is True

        result = vector_service.delete_by_document(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
        )
        assert result["deleted"] is True


# ===================================================================
# Failure Handling
# ===================================================================


class TestVectorFailure:
    """Retry and failure handling."""

    def test_retry_on_transient_failure(self, vector_service, mock_qdrant_client):
        """Transient failures trigger retries and eventually succeed."""
        call_count = {"count": 0}

        def _fail_once(*args, **kwargs):
            call_count["count"] += 1
            if call_count["count"] == 1:
                raise ConnectionError("Transient failure")
            return MagicMock()

        mock_qdrant_client.upsert.side_effect = _fail_once

        vectors = [_make_vector_dict(chunk_id=uuid.uuid4())]
        result = vector_service.upsert_vectors(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            vectors=vectors,
        )

        assert result["upserted_count"] == 1
        assert call_count["count"] >= 1

    def test_retry_exhaustion_raises(self, vector_service, mock_qdrant_client):
        """After exhausting retries, VectorServiceError is raised."""
        mock_qdrant_client.query_points.side_effect = ConnectionError("Persistent failure")

        with pytest.raises(VectorServiceError) as exc_info:
            vector_service.search(
                user_id=TEST_USER_ID,
                query_vector=_random_vector(),
            )

        assert exc_info.value.operation == "search"
        assert "retries" in str(exc_info.value).lower()

    def test_close_reinitializes(self, vector_service, mock_qdrant_client):
        """After close(), next call creates a new client and resets collection flag."""
        import app.services.vector_service as vs_mod

        original_client = vector_service._client
        assert original_client is not None

        # Mark collection as initialized first
        vector_service._collection_initialized = True
        assert vector_service._collection_initialized is True

        vector_service.close()
        assert vector_service._client is None
        assert vector_service._collection_initialized is False

        # Simulate a new QdrantClient instance being created
        # by resetting mock to return a different MagicMock
        new_mock = MagicMock()
        vs_mod.QdrantClient.return_value = new_mock

        # Accessing client re-initializes from the patched QdrantClient class
        vector_service._client = None
        new_client = vector_service.client
        assert new_client is new_mock  # new instance from patched class


# ===================================================================
# Structured Logging
# ===================================================================


class TestVectorLogging:
    """Verify structured logging behaviour — no content leakage."""

    def test_upsert_events_emitted(self, vector_service, mock_qdrant_client, caplog):
        """Upsert emits a structured log event."""
        import logging
        caplog.set_level(logging.INFO, logger="vector_service")
        vectors = [_make_vector_dict(chunk_id=uuid.uuid4())]

        vector_service.upsert_vectors(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            vectors=vectors,
        )

        assert any("vector.upserted" in r.message for r in caplog.records)

    def test_search_events_emitted(self, vector_service, mock_qdrant_client, caplog):
        """Search emits a structured log event."""
        import logging
        caplog.set_level(logging.INFO, logger="vector_service")
        mock_qdrant_client.query_points.return_value = _make_query_response([])

        vector_service.search(
            user_id=TEST_USER_ID,
            query_vector=_random_vector(),
        )

        assert any("vector.searched" in r.message for r in caplog.records)

    def test_delete_events_emitted(self, vector_service, mock_qdrant_client, caplog):
        """Delete emits a structured log event."""
        import logging
        caplog.set_level(logging.INFO, logger="vector_service")

        vector_service.delete_by_document(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
        )

        assert any("vector.deleted_by_document" in r.message for r in caplog.records)

    def test_no_embedding_values_in_logs(self, vector_service, mock_qdrant_client, caplog):
        """Logs must not contain actual embedding vector values."""
        import logging
        caplog.set_level(logging.INFO, logger="vector_service")
        vectors = [_make_vector_dict(chunk_id=uuid.uuid4())]

        vector_service.upsert_vectors(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            vectors=vectors,
        )

        # Logs should contain metadata like count, but not raw vector floats
        log_text = " ".join(r.message for r in caplog.records)
        assert "count" in log_text or "vector.upserted" in log_text
        # Raw vector values should not be in the log
        assert "[-0." not in log_text

    def test_no_document_content_in_logs(self, vector_service, mock_qdrant_client, caplog):
        """Logs must not contain document or chunk text content."""
        import logging
        caplog.set_level(logging.INFO, logger="vector_service")
        secret = "NEVER_LOG_THIS_CONTENT_ABC123"
        vectors = [_make_vector_dict(chunk_id=uuid.uuid4(), overrides={"payload": {"secret": secret}})]

        vector_service.upsert_vectors(
            user_id=TEST_USER_ID,
            document_id=TEST_DOCUMENT_ID,
            vectors=vectors,
        )

        log_text = " ".join(r.message for r in caplog.records)
        assert secret not in log_text


# ===================================================================
# Health Check
# ===================================================================


class TestVectorHealth:
    """Health check functionality."""

    def test_health_check_success(self, vector_service, mock_qdrant_client):
        """Healthy Qdrant returns positive health status."""
        from qdrant_client.http import models as qmodels

        mock_collections = MagicMock()
        mock_coll_item = MagicMock(spec=qmodels.CollectionDescription)
        mock_coll_item.name = settings.QDRANT_COLLECTION
        mock_collections.collections = [mock_coll_item]
        mock_qdrant_client.get_collections.return_value = mock_collections

        health = vector_service.health_check()

        assert health["status"] == "healthy"
        assert health["collection_exists"] is True

    def test_health_check_collection_not_found(self, vector_service, mock_qdrant_client):
        """When collection doesn't exist, health still reports healthy."""
        mock_collections = MagicMock()
        mock_collections.collections = []
        mock_qdrant_client.get_collections.return_value = mock_collections

        health = vector_service.health_check()

        assert health["status"] == "healthy"
        assert health["collection_exists"] is False

    def test_health_check_failure(self, vector_service, mock_qdrant_client):
        """When Qdrant is unavailable, health returns unhealthy."""
        mock_qdrant_client.get_collections.side_effect = ConnectionError("Qdrant unavailable")

        health = vector_service.health_check()

        assert health["status"] == "unhealthy"
        assert "error" in health


# ===================================================================
# Health Service Integration
# ===================================================================


class TestHealthService:
    """Integration of vector service with health endpoint."""

    def test_get_health_aggregates_qdrant(self, mock_qdrant_client):
        """get_health() returns status for all dependencies including Qdrant."""
        from qdrant_client.http import models as qmodels

        mock_collections = MagicMock()
        mock_collections.collections = []
        mock_qdrant_client.get_collections.return_value = mock_collections

        from app.services.health_service import get_health

        health = get_health()
        assert "dependencies" in health
        assert "qdrant" in health["dependencies"]
        assert health["dependencies"]["qdrant"]["status"] in ("healthy", "unhealthy")


# ===================================================================
# Singleton
# ===================================================================


class TestVectorSingleton:
    """Global vector service singleton."""

    def test_get_vector_service_returns_same_instance(self):
        """Repeated calls to get_vector_service return the same instance."""
        import app.services.vector_service as vs_mod
        vs_mod._vector_service = None

        vs1 = get_vector_service()
        vs2 = get_vector_service()
        assert vs1 is vs2
