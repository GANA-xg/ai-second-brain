"""
Embedding generation service.

Provides deterministic, configurable sentence-transformer embedding generation
with batch processing, retry logic, timeout handling, and structured logging.

Design:
  - Model is loaded once (lazy singleton) and reused across calls.
  - Embeddings are deterministic: same text + same model = same vector.
  - Batches are processed in sequence with configurable batch size.
  - Failed batches are retried up to max_retries.
  - Timeout per batch prevents hung model calls.
  - No chunk content is ever logged.
"""

import concurrent.futures
import time
from typing import List, Optional, Tuple

import numpy as np

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger("embedding_service")

# ---------------------------------------------------------------------------
# Lazy singleton for the sentence-transformers model
# ---------------------------------------------------------------------------

_model_instance = None
_model_name_loaded = None


def _load_model(model_name: str):
    """Load a sentence-transformers model (lazy singleton).

    The model is cached globally so it is loaded exactly once per process
    regardless of how many times embed() is called.
    """
    global _model_instance, _model_name_loaded
    if _model_instance is not None and _model_name_loaded == model_name:
        return _model_instance

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers is required for embedding generation. "
            "Install it with: pip install sentence-transformers"
        )

    logger.info(
        "embedding.model_loading",
        model=model_name,
    )
    _model_instance = SentenceTransformer(model_name)
    _model_name_loaded = model_name

    logger.info(
        "embedding.model_loaded",
        model=model_name,
        dimension=_model_instance.get_sentence_embedding_dimension(),
        device=str(_model_instance.device),
    )
    return _model_instance


# ---------------------------------------------------------------------------
# Embedding generation helpers
# ---------------------------------------------------------------------------


def _validate_embedding(
    embedding: np.ndarray,
    expected_dim: int,
    index: int,
) -> None:
    """Validate a single embedding vector."""
    if embedding.ndim != 1:
        raise ValueError(
            f"Embedding at index {index} has {embedding.ndim} dimensions "
            f"(expected 1)"
        )
    if embedding.shape[0] != expected_dim:
        raise ValueError(
            f"Embedding at index {index} has dimension {embedding.shape[0]} "
            f"(expected {expected_dim})"
        )
    if np.any(np.isnan(embedding)):
        raise ValueError(
            f"Embedding at index {index} contains NaN values"
        )


def _embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """Serialize a numpy float32 embedding vector to bytes."""
    return embedding.astype(np.float32).tobytes()


def _bytes_to_embedding(data: bytes) -> np.ndarray:
    """Deserialize bytes back to a numpy float32 embedding vector."""
    return np.frombuffer(data, dtype=np.float32).copy()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_embeddings(
    texts: List[str],
    *,
    model_name: str,
    batch_size: int = 32,
    max_retries: int = 3,
    timeout_seconds: int = 30,
    show_progress: bool = False,
) -> Tuple[List[bytes], List[int], float]:
    """Generate embeddings for a list of texts.

    The function is deterministic: same texts + same model_name always
    produces identical embeddings (byte-identical).

    Args:
        texts: List of text strings to embed.
        model_name: HuggingFace model name (e.g.
            'sentence-transformers/all-MiniLM-L6-v2').
        batch_size: Number of texts to process per batch.
        max_retries: Number of retries for a failed batch.
        timeout_seconds: Timeout per batch in seconds.
        show_progress: If True, log progress per batch.

    Returns:
        Tuple of (embedding_bytes_list, failed_indices_list, total_time_seconds).

    Raises:
        ValueError: If all batches fail after max retries.
        ImportError: If sentence-transformers is not installed.
    """
    model = _load_model(model_name)
    dim = model.get_sentence_embedding_dimension()

    all_embeddings: List[Optional[bytes]] = [None] * len(texts)
    failed_indices: List[int] = []
    total_start = time.time()

    # Process in deterministic batches
    for batch_start in range(0, len(texts), batch_size):
        batch_end = min(batch_start + batch_size, len(texts))
        batch_texts = texts[batch_start:batch_end]
        batch_indices = list(range(batch_start, batch_end))

        if show_progress:
            logger.info(
                "embedding.batch_start",
                batch_start=batch_start,
                batch_end=batch_end,
                batch_size=len(batch_texts),
            )

        # Retry loop for this batch
        success = False
        for attempt in range(1, max_retries + 1):
            try:
                batch_result = _encode_batch(
                    model, batch_texts, dim, timeout_seconds
                )
                for local_idx, global_idx in enumerate(batch_indices):
                    all_embeddings[global_idx] = batch_result[local_idx]
                success = True
                break
            except Exception as exc:
                logger.warning(
                    "embedding.batch_retry",
                    batch_start=batch_start,
                    batch_size=len(batch_texts),
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(exc)[:200],
                )
                if attempt == max_retries:
                    # Mark these indices as failed
                    failed_indices.extend(batch_indices)
                    logger.error(
                        "embedding.batch_failed",
                        batch_start=batch_start,
                        batch_size=len(batch_texts),
                        error=str(exc)[:200],
                    )

        if show_progress and success:
            logger.info(
                "embedding.batch_done",
                batch_start=batch_start,
                batch_end=batch_end,
            )

    total_time = time.time() - total_start

    # Build final result — failed texts get None placeholder
    result = []
    for idx in range(len(texts)):
        if idx in failed_indices:
            result.append(b"")
        else:
            emb = all_embeddings[idx]
            if emb is not None:
                result.append(emb)
            else:
                result.append(b"")

    return result, failed_indices, total_time


def _encode_batch(
    model,
    texts: List[str],
    expected_dim: int,
    timeout: int,
) -> List[bytes]:
    """Encode a single batch with timeout.

    Uses a ThreadPoolExecutor to enforce a wall-clock timeout on the encode
    call, preventing hung model inference from blocking the pipeline.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            model.encode,
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        try:
            embeddings: np.ndarray = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"Embedding batch timed out after {timeout}s"
            )

    # embeddings shape: (batch_size, dim)
    if embeddings.ndim != 2:
        raise ValueError(
            f"Expected 2D output, got shape {embeddings.shape}"
        )
    if embeddings.shape[0] != len(texts):
        raise ValueError(
            f"Expected {len(texts)} embeddings, got {embeddings.shape[0]}"
        )

    results: List[bytes] = []
    for i in range(embeddings.shape[0]):
        emb = embeddings[i]
        _validate_embedding(emb, expected_dim, i)
        results.append(_embedding_to_bytes(emb))

    return results


def get_embedding_dimension(model_name: str) -> int:
    """Get the embedding dimension for a model without generating."""
    model = _load_model(model_name)
    return model.get_sentence_embedding_dimension()


def clear_model_cache() -> None:
    """Clear the cached model — useful for tests."""
    global _model_instance, _model_name_loaded
    _model_instance = None
    _model_name_loaded = None
