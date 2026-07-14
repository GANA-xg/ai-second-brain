"""
Embedding generation pipeline.

Orchestrates batch embedding generation for a document's chunks.

Pipeline:
  Chunks (from DB)
    ↓
  Batch Selection (deterministic ordering by chunk_index)
    ↓
  Sentence Transformer (configurable batch size, retry, timeout)
    ↓
  Embedding Validation (shape, NaN)
    ↓
  Metadata Recording (model, version, dimension)
    ↓
  Persistence (idempotent, replaces old embeddings for same version)
    ↓
  Processing Report (structured log)

Design:
  - Idempotent: re-running replaces embeddings for (chunk_id, embedding_version).
  - Deterministic: same chunks + same model + same version = same output.
  - Full document at a time (not chunk-at-a-time) for batching efficiency.
  - Never logs chunk content.
"""

import time
from typing import List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.chunk import Chunk
from app.models.chunk_embedding import ChunkEmbedding
from app.models.document import Document
from app.services.embedding_service import (
    generate_embeddings,
    get_embedding_dimension,
)
from app.services.vector_service import get_vector_service

logger = get_logger("embedding_pipeline")


class EmbeddingPipeline:
    """Orchestrates embedding generation for a document's chunks."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def process(
        self,
        db: Session,
        document: Document,
    ) -> Document:
        """Generate embeddings for all chunks belonging to a document.

        Steps:
          1. Fetch all chunks for the document (ordered by chunk_index).
          2. Generate embeddings in configurable batches.
          3. Persist embeddings with version metadata (idempotent).
          4. Log structured embedding report.

        Idempotent: re-running replaces old embeddings for the same
        (chunk_id, embedding_version) cleanly.

        Args:
            db: Database session.
            document: Document whose chunks should be embedded.

        Returns:
            The same document (updated in-place via DB session).
        """
        start = time.time()

        model_name = self.settings.EMBEDDING_MODEL
        version = self.settings.EMBEDDING_VERSION

        try:
            # ── Phase 1: Fetch chunks (deterministic order) ────────────
            chunks: List[Chunk] = (
                db.query(Chunk)
                .filter(Chunk.document_id == document.id)
                .order_by(Chunk.chunk_index)
                .all()
            )

            if not chunks:
                logger.info(
                    "embedding.no_chunks",
                    document_id=str(document.id),
                    filename=document.filename,
                )
                return document

            # ── Phase 2: Extract text in chunk_index order ────────────
            texts = [chunk.content for chunk in chunks]
            chunk_ids = [chunk.id for chunk in chunks]

            # ── Phase 3: Generate embeddings ──────────────────────────
            embed_start = time.time()
            embedding_bytes, failed_indices, embed_time = generate_embeddings(
                texts,
                model_name=model_name,
                batch_size=self.settings.EMBEDDING_BATCH_SIZE,
                max_retries=self.settings.EMBEDDING_MAX_RETRIES,
                timeout_seconds=self.settings.EMBEDDING_TIMEOUT_SECONDS,
                show_progress=True,
            )
            embed_total = time.time() - embed_start

            # ── Phase 4: Compute magnitude scores ─────────────────────
            magnitudes = _compute_magnitudes(embedding_bytes)

            # ── Phase 5: Persist (idempotent) ─────────────────────────
            db_start = time.time()

            if embedding_bytes:
                self._persist_embeddings(
                    db=db,
                    chunk_ids=chunk_ids,
                    embedding_bytes=embedding_bytes,
                    model_name=model_name,
                    version=version,
                    magnitudes=magnitudes,
                    failed_indices=failed_indices,
                )

            db_time = time.time() - db_start
            total_time = time.time() - start

            # ── Phase 6: Upsert to Qdrant ───────────────────────────────
            qdrant_start = time.time()
            try:
                self._upsert_to_qdrant(
                    db=db,
                    document=document,
                    chunk_ids=chunk_ids,
                    embedding_bytes=embedding_bytes,
                    failed_indices=failed_indices,
                    model_name=model_name,
                    version=version,
                )
            except Exception as qdrant_exc:
                logger.error(
                    "embedding.qdrant_upsert_failed",
                    document_id=str(document.id),
                    filename=document.filename,
                    error=str(qdrant_exc)[:500],
                )
                # Qdrant failure is non-fatal — embeddings are stored in PG
            qdrant_time = time.time() - qdrant_start
            total_time = time.time() - start

            # ── Phase 7: Log report ────────────────────────────────────
            char_count = sum(len(t) for t in texts)
            self._log_report(
                document=document,
                outcome="success" if len(failed_indices) == 0 else "partial",
                generation_time=embed_total,
                db_time=db_time,
                total_time=total_time,
                total_chunks=len(chunks),
                embedded_chunks=len(chunks) - len(failed_indices),
                failed_chunks=len(failed_indices),
                char_count=char_count,
                model_name=model_name,
                version=version,
            )

            return document

        except Exception as exc:
            total_time = time.time() - start
            self._log_report(
                document=document,
                outcome="failure",
                generation_time=0.0,
                db_time=0.0,
                total_time=total_time,
                total_chunks=0,
                embedded_chunks=0,
                failed_chunks=0,
                char_count=0,
                model_name=model_name,
                version=version,
                failure_reason=str(exc)[:500],
            )
            logger.error(
                "embedding.pipeline_failed",
                document_id=str(document.id),
                filename=document.filename,
                error=str(exc)[:500],
            )
            return document

    def _persist_embeddings(
        self,
        db: Session,
        chunk_ids: List,
        embedding_bytes: List[bytes],
        model_name: str,
        version: str,
        magnitudes: List[Optional[float]],
        failed_indices: List[int],
    ) -> None:
        """Persist embeddings deterministically, replacing old ones.

        Uses the unique constraint on (chunk_id, embedding_version) to
        ensure idempotency: we delete-then-insert for clean replacement.
        """
        dim = get_embedding_dimension(model_name)

        for local_idx, chunk_id in enumerate(chunk_ids):
            if local_idx in failed_indices:
                continue

            emb_bytes = embedding_bytes[local_idx]
            if not emb_bytes:
                continue

            # Delete any existing embedding for this (chunk, version)
            db.query(ChunkEmbedding).filter(
                ChunkEmbedding.chunk_id == chunk_id,
                ChunkEmbedding.embedding_version == version,
            ).delete()

            record = ChunkEmbedding(
                chunk_id=chunk_id,
                embedding=emb_bytes,
                embedding_model=model_name,
                embedding_version=version,
                embedding_dimension=dim,
                magnitude=magnitudes[local_idx],
            )
            db.add(record)

        db.commit()

    def _upsert_to_qdrant(
        self,
        db: Session,
        document: Document,
        chunk_ids: List,
        embedding_bytes: List[bytes],
        failed_indices: List[int],
        model_name: str,
        version: str,
    ) -> None:
        """Upsert embeddings to Qdrant vector database.

        Builds vectors with payload metadata and upserts them.
        Deterministic point IDs ensure idempotency on reruns.
        """
        vectors = []
        for local_idx, chunk_id in enumerate(chunk_ids):
            if local_idx in failed_indices:
                continue

            emb_bytes = embedding_bytes[local_idx]
            if not emb_bytes:
                continue

            # Convert bytes to float list
            import numpy as np
            vector = np.frombuffer(emb_bytes, dtype=np.float32).tolist()

            # Get chunk for payload metadata
            chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
            if not chunk:
                continue

            payload = {
                "chunk_index": chunk.chunk_index,
                "embedding_version": version,
                "embedding_model": model_name,
                "source_type": chunk.source_type,
                "page_number": chunk.page_number,
                "slide_number": chunk.slide_number,
                "section": chunk.section,
                "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
            }

            vectors.append(
                {
                    "chunk_id": chunk_id,
                    "vector": vector,
                    "payload": payload,
                }
            )

        if vectors:
            vector_service = get_vector_service()
            vector_service.upsert_vectors(
                user_id=document.user_id,
                document_id=document.id,
                vectors=vectors,
            )

    def _log_report(
        self,
        document: Document,
        outcome: str,
        generation_time: float,
        db_time: float,
        total_time: float,
        total_chunks: int,
        embedded_chunks: int,
        failed_chunks: int,
        char_count: int,
        model_name: str,
        version: str,
        failure_reason: Optional[str] = None,
    ) -> None:
        """Emit a structured log entry — never logs chunk content."""
        log_data = {
            "document_id": str(document.id),
            "filename": document.filename,
            "extension": document.extension,
            "outcome": outcome,
            "model": model_name,
            "version": version,
            "total_chunks": total_chunks,
            "embedded_chunks": embedded_chunks,
            "failed_chunks": failed_chunks,
            "char_count": char_count,
            "generation_time_ms": round(generation_time * 1000, 2),
            "db_time_ms": round(db_time * 1000, 2),
            "total_time_ms": round(total_time * 1000, 2),
        }

        if failure_reason:
            log_data["failure_reason"] = failure_reason

        if outcome == "success":
            logger.info("embedding.document_embedded", **log_data)
        elif outcome == "partial":
            logger.warning("embedding.document_partially_embedded", **log_data)
        else:
            logger.error("embedding.document_embedding_failed", **log_data)


def _compute_magnitudes(
    embedding_bytes: List[bytes],
) -> List[Optional[float]]:
    """Compute L2 magnitude for each embedding (or None if failed)."""
    magnitudes: List[Optional[float]] = []
    for emb_bytes in embedding_bytes:
        if not emb_bytes:
            magnitudes.append(None)
        else:
            arr = np.frombuffer(emb_bytes, dtype=np.float32)
            mag = float(np.linalg.norm(arr))
            magnitudes.append(mag)
    return magnitudes
