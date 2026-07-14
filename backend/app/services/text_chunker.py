"""
Deterministic character-based text chunking.

Chunks are split on character boundaries with configurable overlap.
The algorithm always produces the same output for the same input
(config + text), guaranteeing that future embedding systems receive
identical chunks for identical documents.

Chunking avoids tiny trailing chunks by extending the last full chunk
to include the remainder when the remaining text is less than 20% of
the chunk size.

Each chunk carries metadata: index, character range, and a token
estimate (chars / 4, minimum 1).
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class ChunkResult:
    """A single chunk with its metadata."""

    chunk_index: int
    content: str
    character_start: int
    character_end: int
    token_estimate: int
    page_number: int | None = None
    slide_number: int | None = None
    section: str | None = None


@dataclass
class ChunkingReport:
    """Report from a chunking operation."""

    chunk_count: int
    total_chars: int
    chunk_size: int
    overlap: int
    chunks: List[ChunkResult] = field(default_factory=list)


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 200,
    page_number: int | None = None,
    slide_number: int | None = None,
    section: str | None = None,
) -> ChunkingReport:
    """Split normalized text into deterministic chunks.

    Args:
        text: Normalized text to chunk.
        chunk_size: Maximum characters per chunk.
        overlap: Number of overlapping characters between consecutive chunks.
        page_number: Optional page number to attach to all chunks.
        slide_number: Optional slide number to attach to all chunks.
        section: Optional section heading to attach to all chunks.

    Returns:
        A ChunkingReport containing all chunks and metadata.

    Raises:
        ValueError: If chunk_size <= overlap or chunk_size <= 0 or overlap < 0.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be less than chunk_size")
    if not text:
        return ChunkingReport(
            chunk_count=0,
            total_chars=0,
            chunk_size=chunk_size,
            overlap=overlap,
            chunks=[],
        )

    chunks: List[ChunkResult] = []
    index = 0
    start = 0
    text_len = len(text)

    while start < text_len:
        # Determine end of this chunk
        end = start + chunk_size

        if end >= text_len:
            # Last chunk — take remaining text
            end = text_len
            chunk_text = text[start:end]

            # If this would be a tiny trailing chunk (< 20% of chunk_size)
            # and there are previous chunks, merge into the last one
            tiny_threshold = max(1, int(chunk_size * 0.2))
            if (
                len(chunk_text) < tiny_threshold
                and index > 0
                and chunks
            ):
                prev = chunks[-1]
                prev.content += chunk_text
                prev.character_end = end
                prev.token_estimate = max(1, len(prev.content) // 4)
                break

            chunks.append(
                ChunkResult(
                    chunk_index=index,
                    content=chunk_text,
                    character_start=start,
                    character_end=end,
                    token_estimate=max(1, len(chunk_text) // 4),
                    page_number=page_number,
                    slide_number=slide_number,
                    section=section,
                )
            )
            break

        chunk_text = text[start:end]

        # Check for tiny trailing text — if remaining is small,
        # extend this chunk to absorb the rest
        remaining = text_len - end
        tiny_threshold = max(1, int(chunk_size * 0.2))
        if 0 < remaining < tiny_threshold:
            end = text_len
            chunk_text = text[start:end]

        chunks.append(
            ChunkResult(
                chunk_index=index,
                content=chunk_text,
                character_start=start,
                character_end=end,
                token_estimate=max(1, len(chunk_text) // 4),
                page_number=page_number,
                slide_number=slide_number,
                section=section,
            )
        )

        if end >= text_len:
            break

        index += 1
        start = end - overlap

    return ChunkingReport(
        chunk_count=len(chunks),
        total_chars=text_len,
        chunk_size=chunk_size,
        overlap=overlap,
        chunks=chunks,
    )
