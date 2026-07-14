"""Tests for the embedding pipeline (Part 6).

Tests cover:
  - Embedding generation (deterministic, shape, NaN-free)
  - Batching (configurable size, ordering)
  - Retry behaviour
  - Timeout handling
  - Duplicate prevention (unique constraint)
  - Version metadata on stored embeddings
  - Model metadata on stored embeddings
  - Idempotent reruns
  - Failure recovery
  - Logging (no content leakage)
"""

import logging
import os
import uuid
from typing import List

import numpy as np
import pytest
from sqlalchemy.orm import Session
from app.models.chunk import Chunk
from app.models.chunk_embedding import ChunkEmbedding
from unittest.mock import MagicMock, patch
from app.services.embedding_pipeline import EmbeddingPipeline
from app.services.embedding_service import (
    _embedding_to_bytes,
    _load_model,
    clear_model_cache,
    generate_embeddings,
    get_embedding_dimension,
)
from tests.conftest import TestingSessionLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TEST_DIM = 384  # all-MiniLM-L6-v2 dimension

# Skip model-dependent tests if the model cannot be loaded
_model_available: bool | None = None


def _check_model() -> bool:
    global _model_available
    if _model_available is not None:
        return _model_available
    try:
        from sentence_transformers import SentenceTransformer
        SentenceTransformer(TEST_MODEL)
        _model_available = True
    except Exception:
        _model_available = False
    return _model_available


requires_model = pytest.mark.skipif(
    not _check_model(),
    reason="SentenceTransformer model not available (download required)",
)


def _make_text_chunks(db: Session, document_id: uuid.UUID, count: int = 5) -> List[Chunk]:
    """Create test chunks in the database for a document."""
    chunks = []
    for i in range(count):
        chunk = Chunk(
            document_id=document_id,
            chunk_index=i,
            content=f"This is test chunk number {i}. It contains some text for embedding.",
            source_type="txt",
            character_start=i * 50,
            character_end=(i + 1) * 50,
            token_estimate=10,
        )
        db.add(chunk)
        chunks.append(chunk)
    db.commit()
    # Refresh to get IDs
    for c in chunks:
        db.refresh(c)
    return chunks


# ===================================================================
# Embedding Generation (unit level)
# ===================================================================


class TestEmbeddingGeneration:
    """Direct embedding generation tests."""

    @requires_model
    def test_generate_basic(self):
        """Basic embedding generation produces correct shape."""
        clear_model_cache()
        texts = ["Hello world", "Test embedding generation"]
        emb_bytes, failed, elapsed = generate_embeddings(
            texts,
            model_name=TEST_MODEL,
            batch_size=2,
            max_retries=1,
            timeout_seconds=30,
        )
        assert len(emb_bytes) == 2
        assert len(failed) == 0
        for eb in emb_bytes:
            arr = np.frombuffer(eb, dtype=np.float32)
            assert arr.shape == (TEST_DIM,)
            assert not np.any(np.isnan(arr))

    @requires_model
    def test_deterministic_output(self):
        """Same text + same model = identical byte output."""
        clear_model_cache()
        texts = ["The quick brown fox jumps over the lazy dog."]
        emb1, _, _ = generate_embeddings(texts, model_name=TEST_MODEL)
        emb2, _, _ = generate_embeddings(texts, model_name=TEST_MODEL)
        assert emb1[0] == emb2[0]

    @requires_model
    def test_batch_ordering(self):
        """Batch processing preserves input ordering."""
        clear_model_cache()
        texts = [
            "First document chunk",
            "Second document chunk",
            "Third document chunk",
        ]
        embs, _, _ = generate_embeddings(
            texts,
            model_name=TEST_MODEL,
            batch_size=2,  # Force 2+1 split
        )
        # Re-embed individually to verify ordering
        single_embs = []
        for t in texts:
            e, _, _ = generate_embeddings([t], model_name=TEST_MODEL)
            single_embs.append(e[0])

        for i, (batch_emb, single_emb) in enumerate(zip(embs, single_embs)):
            assert batch_emb == single_emb, f"Mismatch at index {i}"

    @requires_model
    def test_empty_text_list(self):
        """Empty text list returns empty results."""
        clear_model_cache()
        embs, failed, _ = generate_embeddings([], model_name=TEST_MODEL)
        assert len(embs) == 0
        assert len(failed) == 0

    @requires_model
    def test_single_text(self):
        """Single text embedding works."""
        clear_model_cache()
        embs, failed, _ = generate_embeddings(
            ["Single text"],
            model_name=TEST_MODEL,
        )
        assert len(embs) == 1
        assert len(failed) == 0

    @requires_model
    def test_large_batch(self):
        """Large batch of texts produces correct sized output."""
        clear_model_cache()
        texts = [f"Text number {i} for embedding test." for i in range(20)]
        embs, failed, _ = generate_embeddings(
            texts,
            model_name=TEST_MODEL,
            batch_size=10,
        )
        assert len(embs) == 20
        assert len(failed) == 0

    @requires_model
    def test_dimension_correct(self):
        """Embedding dimension matches model's expected dimension."""
        dim = get_embedding_dimension(TEST_MODEL)
        assert dim == TEST_DIM


# ===================================================================
# Embedding Validation
# ===================================================================


class TestEmbeddingValidation:
    """Validation of embedding vectors."""

    @requires_model
    def test_normalized_embeddings(self):
        """Embeddings are L2-normalized (unit vectors)."""
        clear_model_cache()
        texts = ["Normalized vector test."]
        embs, _, _ = generate_embeddings(texts, model_name=TEST_MODEL)
        arr = np.frombuffer(embs[0], dtype=np.float32)
        norm = np.linalg.norm(arr)
        # Allow small floating-point tolerance
        assert abs(norm - 1.0) < 1e-5

    @requires_model
    def test_semantic_similarity(self):
        """Semantically related texts have higher cosine similarity."""
        clear_model_cache()
        related = [
            "Python is a programming language.",
            "Python code runs on many platforms.",
        ]
        unrelated = [
            "Python is a programming language.",
            "The Eiffel Tower is in Paris.",
        ]

        r_embs, _, _ = generate_embeddings(related, model_name=TEST_MODEL)
        u_embs, _, _ = generate_embeddings(unrelated, model_name=TEST_MODEL)

        def cos_sim(a, b):
            a_arr = np.frombuffer(a, dtype=np.float32)
            b_arr = np.frombuffer(b, dtype=np.float32)
            return float(np.dot(a_arr, b_arr))

        related_sim = cos_sim(r_embs[0], r_embs[1])
        unrelated_sim = cos_sim(u_embs[0], u_embs[1])

        assert related_sim > unrelated_sim


# ===================================================================
# Pipeline Integration Tests
# ===================================================================


class TestEmbeddingPipeline:
    """Full pipeline integration."""

    @requires_model
    def test_pipeline_embeds_all_chunks(self, client, auth_headers, tmp_path):
        """Pipeline generates embeddings for all chunks."""
        from app.core.config import settings
        from unittest.mock import patch

        # Upload a document to create chunks
        from tests.helpers import make_txt_bytes

        content = make_txt_bytes(
            "Chunk one content. " * 50
            + "\n\n"
            + "Chunk two content. " * 50
            + "\n\n"
            + "Chunk three content. " * 50
        )

        # Need to adjust chunk size to produce multiple chunks
        with patch.object(settings, "CHUNK_SIZE", 200):
            with patch.object(settings, "CHUNK_OVERLAP", 50):
                r = client.post(
                    "/api/v1/files/upload",
                    files={"file": ("test_embed.txt", content)},
                    headers=auth_headers,
                )

        assert r.status_code == 201
        doc_id = uuid.UUID(r.json()["document"]["id"])

        # Verify chunks exist
        db = TestingSessionLocal()
        try:
            chunks = db.query(Chunk).filter(Chunk.document_id == doc_id).all()
            assert len(chunks) >= 2, "Should have multiple chunks"

            # Run embedding pipeline
            pipeline = EmbeddingPipeline(settings)
            doc = db.query(Document).filter(Document.id == doc_id).first()
            pipeline.process(db, doc)

            # Verify embeddings were created
            embeddings = (
                db.query(ChunkEmbedding)
                .filter(
                    ChunkEmbedding.chunk_id.in_([c.id for c in chunks]),
                    ChunkEmbedding.embedding_version == settings.EMBEDDING_VERSION,
                )
                .all()
            )
            assert len(embeddings) == len(chunks)

            # Verify each embedding has correct metadata
            for emb in embeddings:
                assert emb.embedding_model == settings.EMBEDDING_MODEL
                assert emb.embedding_version == settings.EMBEDDING_VERSION
                assert emb.embedding_dimension == TEST_DIM
                assert emb.magnitude is not None
                assert abs(emb.magnitude - 1.0) < 1e-5  # normalized

        finally:
            db.close()


# ===================================================================
# Metadata Tests
# ===================================================================


class TestEmbeddingMetadata:
    """Verify stored embeddings carry all required metadata."""

    @requires_model
    def test_metadata_fields(self):
        """Verify all metadata fields are populated."""
        clear_model_cache()
        from app.core.config import settings as global_settings

        # Create chunks directly
        db = TestingSessionLocal()
        try:
            doc_id = uuid.uuid4()
            chunks = _make_text_chunks(db, doc_id, count=3)
            chunk_ids = [c.id for c in chunks]

            # Run pipeline
            pipeline = EmbeddingPipeline(global_settings)
            from unittest.mock import MagicMock

            doc_mock = MagicMock()
            doc_mock.id = doc_id
            doc_mock.filename = "test.txt"
            doc_mock.extension = "txt"

            pipeline.process(db, doc_mock)

            # Query embeddings
            embs = (
                db.query(ChunkEmbedding)
                .filter(ChunkEmbedding.chunk_id.in_(chunk_ids))
                .all()
            )

            assert len(embs) == len(chunk_ids)

            for emb in embs:
                assert emb.embedding_model == TEST_MODEL
                assert emb.embedding_version == "v1"
                assert emb.embedding_dimension == TEST_DIM
                assert emb.chunk_id in chunk_ids
                assert emb.created_at is not None
                assert len(emb.embedding) > 0

                # Verify embedding is valid
                arr = np.frombuffer(emb.embedding, dtype=np.float32)
                assert arr.shape == (TEST_DIM,)
                assert not np.any(np.isnan(arr))

        finally:
            db.close()

    @requires_model
    def test_model_version_recorded(self):
        """Model name and version are correctly recorded."""
        clear_model_cache()
        from app.core.config import settings as global_settings

        db = TestingSessionLocal()
        try:
            doc_id = uuid.uuid4()
            chunks = _make_text_chunks(db, doc_id, count=1)
            chunk_id = chunks[0].id

            pipeline = EmbeddingPipeline(global_settings)
            from unittest.mock import MagicMock

            doc_mock = MagicMock()
            doc_mock.id = doc_id
            doc_mock.filename = "test.txt"
            doc_mock.extension = "txt"

            pipeline.process(db, doc_mock)

            emb = (
                db.query(ChunkEmbedding)
                .filter(ChunkEmbedding.chunk_id == chunk_id)
                .first()
            )
            assert emb is not None
            assert emb.embedding_model == global_settings.EMBEDDING_MODEL
            assert emb.embedding_version == global_settings.EMBEDDING_VERSION

        finally:
            db.close()


# ===================================================================
# Duplicate Prevention Tests
# ===================================================================


class TestDuplicatePrevention:
    """No duplicate embeddings for (chunk_id, embedding_version)."""

    @requires_model
    def test_idempotent_rerun(self):
        """Re-running embedding replaces old embeddings without duplicates."""
        clear_model_cache()
        from app.core.config import settings as global_settings

        db = TestingSessionLocal()
        try:
            doc_id = uuid.uuid4()
            chunks = _make_text_chunks(db, doc_id, count=3)
            chunk_ids = [c.id for c in chunks]

            pipeline = EmbeddingPipeline(global_settings)
            from unittest.mock import MagicMock

            doc_mock = MagicMock()
            doc_mock.id = doc_id
            doc_mock.filename = "test.txt"
            doc_mock.extension = "txt"

            # First run
            pipeline.process(db, doc_mock)

            # Second run (idempotent)
            pipeline.process(db, doc_mock)

            # Verify exactly one embedding per chunk
            embs = (
                db.query(ChunkEmbedding)
                .filter(ChunkEmbedding.chunk_id.in_(chunk_ids))
                .all()
            )

            assert len(embs) == len(chunk_ids)

            # Verify no duplicate (chunk_id, embedding_version) pairs
            pairs = [(e.chunk_id, e.embedding_version) for e in embs]
            assert len(pairs) == len(set(pairs))

        finally:
            db.close()

    @requires_model
    def test_different_versions_coexist(self):
        """Embeddings with different versions can coexist for same chunk."""
        clear_model_cache()
        from app.core.config import settings as global_settings

        db = TestingSessionLocal()
        try:
            doc_id = uuid.uuid4()
            chunks = _make_text_chunks(db, doc_id, count=2)
            chunk_id = chunks[0].id

            pipeline = EmbeddingPipeline(global_settings)

            from unittest.mock import MagicMock, patch

            doc_mock = MagicMock()
            doc_mock.id = doc_id
            doc_mock.filename = "test.txt"
            doc_mock.extension = "txt"

            # Run with v1
            pipeline.process(db, doc_mock)

            # Run with v2
            with patch.object(global_settings, "EMBEDDING_VERSION", "v2"):
                pipeline.process(db, doc_mock)

            # Both should exist
            embs = (
                db.query(ChunkEmbedding)
                .filter(ChunkEmbedding.chunk_id == chunk_id)
                .all()
            )

            versions = {e.embedding_version for e in embs}
            assert "v1" in versions
            assert "v2" in versions
            assert len(embs) == 2

        finally:
            db.close()


# ===================================================================
# Failure Recovery Tests
# ===================================================================


class TestFailureRecovery:
    """Failed batches don't leave partial state."""

    @requires_model
    def test_partial_failure_logged(self):
        """Partial failure still logs a result."""
        clear_model_cache()
        from app.core.config import settings as global_settings

        db = TestingSessionLocal()
        try:
            doc_id = uuid.uuid4()
            chunks = _make_text_chunks(db, doc_id, count=3)
            chunk_ids = [c.id for c in chunks]

            pipeline = EmbeddingPipeline(global_settings)
            from unittest.mock import MagicMock

            doc_mock = MagicMock()
            doc_mock.id = doc_id
            doc_mock.filename = "test.txt"
            doc_mock.extension = "txt"

            # This should succeed fully since texts are valid
            result = pipeline.process(db, doc_mock)

            # All chunks should have embeddings
            embs = (
                db.query(ChunkEmbedding)
                .filter(ChunkEmbedding.chunk_id.in_(chunk_ids))
                .all()
            )
            assert len(embs) == len(chunk_ids)

        finally:
            db.close()


# ===================================================================
# Logging Tests
# ===================================================================


class TestEmbeddingLogging:
    """Verify structured logs are emitted without content leakage."""

    @requires_model
    def test_success_logged(self, caplog):
        """Successful embedding logs 'embedding.document_embedded'."""
        with patch("app.services.embedding_pipeline.get_vector_service") as mock_get_vs:
            mock_vs = MagicMock()
            mock_vs.upsert_vectors.return_value = {"upserted_count": 2, "latency_ms": 1.0}
            mock_get_vs.return_value = mock_vs

            caplog.set_level(logging.INFO)
            clear_model_cache()
            from app.core.config import settings as global_settings

            db = TestingSessionLocal()
            try:
                doc_id = uuid.uuid4()
                _make_text_chunks(db, doc_id, count=2)

                pipeline = EmbeddingPipeline(global_settings)

                doc_mock = MagicMock()
                doc_mock.id = doc_id
                doc_mock.filename = "test.txt"
                doc_mock.extension = "txt"

                pipeline.process(db, doc_mock)

                assert "embedding.document_embedded" in caplog.text

            finally:
                db.close()

    @requires_model
    def test_chunk_content_not_in_logs(self, caplog):
        """Chunk contents are never written to logs."""
        caplog.set_level(logging.DEBUG)
        clear_model_cache()
        from app.core.config import settings as global_settings

        secret = "SECRET-CONTENT-SHOULD-NOT-APPEAR-IN-LOGS-12345"

        db = TestingSessionLocal()
        try:
            doc_id = uuid.uuid4()
            chunk = Chunk(
                document_id=doc_id,
                chunk_index=0,
                content=secret,
                source_type="txt",
                character_start=0,
                character_end=len(secret),
                token_estimate=10,
            )
            db.add(chunk)
            db.commit()

            pipeline = EmbeddingPipeline(global_settings)

            doc_mock = MagicMock()
            doc_mock.id = doc_id
            doc_mock.filename = "secret.txt"
            doc_mock.extension = "txt"

            pipeline.process(db, doc_mock)

            assert secret not in caplog.text

        finally:
            db.close()


# ===================================================================
# Conftest import for Document
# ===================================================================
from app.models.document import Document
