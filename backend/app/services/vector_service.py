"""
Qdrant vector database service.

Provides collection management, vector upsert, search, and delete operations
with user isolation, retries, timeouts, and structured logging.

Security: Every search operation requires a user_id filter. No unfiltered
searches are possible through this service.
"""

import time
import uuid
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("vector_service")


class VectorServiceError(Exception):
    """Raised when vector service operations fail."""

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        collection: str,
        retries: int,
        last_error: Optional[str] = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.collection = collection
        self.retries = retries
        self.last_error = last_error


class VectorService:
    """Manages Qdrant vector operations with user isolation and retry logic."""

    def __init__(self):
        self._client: Optional[QdrantClient] = None
        self._collection_name = settings.QDRANT_COLLECTION
        self._collection_initialized = False

    @property
    def client(self) -> QdrantClient:
        """Lazy-initialized Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY or None,
                timeout=settings.QDRANT_TIMEOUT_SECONDS,
            )
            logger.info(
                "vector.client_initialized",
                url=settings.QDRANT_URL,
                collection=self._collection_name,
            )
        return self._client

    # ------------------------------------------------------------------
    # Collection Management
    # ------------------------------------------------------------------

    def ensure_collection(self) -> None:
        """Create collection if it doesn't exist. Idempotent."""
        try:
            self.client.get_collection(self._collection_name)
            logger.debug(
                "vector.collection_exists",
                collection=self._collection_name,
            )
        except UnexpectedResponse as exc:
            if exc.status_code == 404:
                self._with_retry(
                    operation="create_collection",
                    func=self._create_collection,
                )
            else:
                raise

    def _create_collection(self) -> None:
        """Create the vector collection with proper schema."""
        self.client.create_collection(
            collection_name=self._collection_name,
            vectors_config=qmodels.VectorParams(
                size=settings.VECTOR_DIMENSION,
                distance=qmodels.Distance[settings.VECTOR_DISTANCE.upper()],
            ),
        )
        # Create explicit payload indexes for common filters
        for field in ("user_id", "document_id", "chunk_id"):
            try:
                self.client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                # Index may already exist
                pass

        logger.info(
            "vector.collection_created",
            collection=self._collection_name,
            dimension=settings.VECTOR_DIMENSION,
            distance=settings.VECTOR_DISTANCE,
        )

    def delete_collection(self) -> None:
        """Delete the entire collection. Use with caution."""
        try:
            self.client.delete_collection(self._collection_name)
            logger.warning(
                "vector.collection_deleted",
                collection=self._collection_name,
            )
        except UnexpectedResponse as exc:
            if exc.status_code != 404:
                raise

    # ------------------------------------------------------------------
    # Vector Upsert
    # ------------------------------------------------------------------

    def upsert_vectors(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        vectors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Upsert vectors for a document's chunks.

        Args:
            user_id: Owning user (enforced in payload for isolation)
            document_id: Parent document ID
            vectors: List of dicts with keys:
                - chunk_id: UUID of the chunk
                - vector: List[float] embedding vector
                - payload: Optional additional metadata

        Returns:
            Dict with operation stats: upserted_count, latency_ms
        """

        # Ensure the collection exists before the first upsert.
        if not self._collection_initialized:
            self.ensure_collection()
            self._collection_initialized = True

        if not vectors:
            return {"upserted_count": 0, "latency_ms": 0.0}

        points = []
        for v in vectors:
            chunk_id = v["chunk_id"]
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}:{chunk_id}"))

            payload = {
                "user_id": str(user_id),
                "document_id": str(document_id),
                "chunk_id": str(chunk_id),
            }
            if "payload" in v:
                payload.update(v["payload"])

            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=v["vector"],
                    payload=payload,
                )
            )

        start = time.time()
        self._with_retry(
            operation="upsert",
            func=lambda: self.client.upsert(
                collection_name=self._collection_name,
                points=points,
                wait=True,
            ),
        )
        elapsed_ms = (time.time() - start) * 1000

        logger.info(
            "vector.upserted",
            collection=self._collection_name,
            user_id=str(user_id),
            document_id=str(document_id),
            count=len(points),
            latency_ms=round(elapsed_ms, 2),
        )

        return {
            "upserted_count": len(points),
            "latency_ms": round(elapsed_ms, 2),
        }
    # ------------------------------------------------------------------
    # Vector Search
    # ------------------------------------------------------------------

    def search(
        self,
        *,
        user_id: uuid.UUID,
        query_vector: list[float],
        limit: int = 10,
        document_ids: Optional[list[uuid.UUID]] = None,
        score_threshold: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """
        Search for similar vectors with mandatory user_id filter.

        Args:
            user_id: Owning user — enforced as filter (security requirement)
            query_vector: Embedding vector to search for
            limit: Max results to return
            document_ids: Optional filter to specific documents
            score_threshold: Minimum similarity score (0-1 for cosine)

        Returns:
            List of results with: chunk_id, document_id, score, payload
        """
        filter_conditions = [
            qmodels.FieldCondition(
                key="user_id",
                match=qmodels.MatchValue(value=str(user_id)),
            )
        ]

        if document_ids:
            filter_conditions.append(
                qmodels.FieldCondition(
                    key="document_id",
                    match=qmodels.MatchAny(any=[str(d) for d in document_ids]),
                )
            )

        query_filter = qmodels.Filter(must=filter_conditions)

        start = time.time()
        search_result = self._with_retry(
            operation="search",
            func=lambda: self.client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False,
            ),
        )
        elapsed_ms = (time.time() - start) * 1000

        formatted = []
        for hit in search_result.points:
            payload = hit.payload or {}
            formatted.append(
                {
                    "chunk_id": payload.get("chunk_id"),
                    "document_id": payload.get("document_id"),
                    "score": hit.score,
                    "payload": payload,
                }
            )

        logger.info(
            "vector.searched",
            collection=self._collection_name,
            user_id=str(user_id),
            query_limit=limit,
            results_returned=len(formatted),
            latency_ms=round(elapsed_ms, 2),
        )
        return formatted

    # ------------------------------------------------------------------
    # Vector Delete
    # ------------------------------------------------------------------

    def delete_by_document(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Delete all vectors for a document (user-scoped)."""
        filter_ = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="user_id", match=qmodels.MatchValue(value=str(user_id))
                ),
                qmodels.FieldCondition(
                    key="document_id", match=qmodels.MatchValue(value=str(document_id))
                ),
            ]
        )

        start = time.time()
        result = self._with_retry(
            operation="delete_by_document",
            func=lambda: self.client.delete(
                collection_name=self._collection_name,
                points_selector=qmodels.FilterSelector(filter=filter_),
                wait=True,
            ),
        )
        elapsed_ms = (time.time() - start) * 1000

        logger.info(
            "vector.deleted_by_document",
            collection=self._collection_name,
            user_id=str(user_id),
            document_id=str(document_id),
            latency_ms=round(elapsed_ms, 2),
        )
        return {"deleted": True, "latency_ms": round(elapsed_ms, 2)}

    def delete_by_chunk(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        chunk_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Delete a specific chunk's vector (user-scoped)."""
        filter_ = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="user_id", match=qmodels.MatchValue(value=str(user_id))
                ),
                qmodels.FieldCondition(
                    key="document_id", match=qmodels.MatchValue(value=str(document_id))
                ),
                qmodels.FieldCondition(
                    key="chunk_id", match=qmodels.MatchValue(value=str(chunk_id))
                ),
            ]
        )

        start = time.time()
        result = self._with_retry(
            operation="delete_by_chunk",
            func=lambda: self.client.delete(
                collection_name=self._collection_name,
                points_selector=qmodels.FilterSelector(filter=filter_),
                wait=True,
            ),
        )
        elapsed_ms = (time.time() - start) * 1000

        logger.info(
            "vector.deleted_by_chunk",
            collection=self._collection_name,
            user_id=str(user_id),
            document_id=str(document_id),
            chunk_id=str(chunk_id),
            latency_ms=round(elapsed_ms, 2),
        )
        return {"deleted": True, "latency_ms": round(elapsed_ms, 2)}

    # ------------------------------------------------------------------
    # Health Check
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """Check Qdrant connectivity and collection status."""
        try:
            start = time.time()
            collections = self.client.get_collections()
            latency_ms = (time.time() - start) * 1000

            collection_exists = any(
                c.name == self._collection_name for c in collections.collections
            )

            return {
                "status": "healthy",
                "collection": self._collection_name,
                "collection_exists": collection_exists,
                "latency_ms": round(latency_ms, 2),
            }
        except Exception as exc:
            logger.error(
                "vector.health_check_failed",
                collection=self._collection_name,
                error=str(exc)[:200],
            )
            return {
                "status": "unhealthy",
                "collection": self._collection_name,
                "error": str(exc)[:200],
            }

    # ------------------------------------------------------------------
    # Internal Retry Logic
    # ------------------------------------------------------------------

    def _with_retry(self, operation: str, func):
        """Execute function with retry logic."""
        last_error = None
        for attempt in range(1, settings.QDRANT_MAX_RETRIES + 1):
            try:
                return func()
            except Exception as exc:
                last_error = str(exc)[:500]
                logger.warning(
                    "vector.operation_retry",
                    operation=operation,
                    collection=self._collection_name,
                    attempt=attempt,
                    max_retries=settings.QDRANT_MAX_RETRIES,
                    error=last_error,
                )
                if attempt == settings.QDRANT_MAX_RETRIES:
                    logger.error(
                        "vector.operation_failed",
                        operation=operation,
                        collection=self._collection_name,
                        retries=attempt,
                        error=last_error,
                    )
                    raise VectorServiceError(
                        f"Vector {operation} failed after {attempt} retries",
                        operation=operation,
                        collection=self._collection_name,
                        retries=attempt,
                        last_error=last_error,
                    )
                time.sleep(0.5 * attempt)  # Exponential backoff base

    def close(self) -> None:
        """Close the client connection. Next access re-creates it."""
        if self._client:
            self._client.close()
            self._client = None
            self._collection_initialized = False
            logger.info("vector.client_closed", collection=self._collection_name)


# Global instance
_vector_service: Optional[VectorService] = None


def get_vector_service() -> VectorService:
    """Get or create the global vector service instance."""
    global _vector_service
    if _vector_service is None:
        _vector_service = VectorService()
    return _vector_service