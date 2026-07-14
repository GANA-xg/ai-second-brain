"""
Document processing pipeline.

Orchestrates the full extraction → normalization → chunking → storage
flow for uploaded documents. Guarantees idempotent reprocessing and
transactional integrity.

Pipeline:
  Document (uploaded)
    ↓
  Text Extraction (PDF/DOCX/PPTX/TXT)
    ↓
  Normalization (Unicode, whitespace, line endings)
    ↓
  Chunking (character-based, configurable overlap)
    ↓
  Metadata Generation (page, slide, section lookup)
    ↓
  Database Storage (idempotent, replaces old chunks)
    ↓
  Processing Report (structured log)
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.services.text_extractor import ExtractionResult, get_extractor
from app.services.text_normalizer import normalize_text
from app.services.text_chunker import ChunkResult as ChunkingChunkResult
from app.services.text_chunker import chunk_text

logger = get_logger("processing_pipeline")


# --------------------------------------------------------------------------- #
# Position-aware text assembly
# --------------------------------------------------------------------------- #

@dataclass
class TextSegment:
    """A continuous piece of text from one extraction unit with metadata."""

    text: str
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    section: Optional[str] = None


@dataclass
class AssembledText:
    """Full assembled text with a position-to-metadata index."""

    full_text: str
    offsets: List[Tuple[int, int, Optional[int], Optional[int], Optional[str]]]
    # offsets: list of (char_start, char_end, page_number, slide_number, section)


def _assemble_text(
    extraction_results: List[ExtractionResult],
) -> AssembledText:
    """Flatten extraction results into continuous text with position index.

    Each extraction unit's text is normalized independently, then concatenated
    with a double newline boundary marker between units. The offset index
    maps character ranges in the full text back to source metadata.

    Args:
        extraction_results: Raw extraction results (pages, slides, etc.).

    Returns:
        An AssembledText with full_text and an offset index.
    """
    parts: List[TextSegment] = []
    for r in extraction_results:
        norm = normalize_text(r.text, preserve_boundaries=True)
        if norm:
            parts.append(
                TextSegment(
                    text=norm,
                    page_number=r.page_number,
                    slide_number=r.slide_number,
                    section=r.section,
                )
            )

    if not parts:
        return AssembledText(full_text="", offsets=[])

    full_text = ""
    offsets: List[
        Tuple[int, int, Optional[int], Optional[int], Optional[str]]
    ] = []

    for i, seg in enumerate(parts):
        start = len(full_text)
        if i > 0:
            full_text += "\n\n"  # page/slide boundary separator
            start = len(full_text)
        full_text += seg.text
        end = len(full_text)
        offsets.append(
            (start, end, seg.page_number, seg.slide_number, seg.section)
        )

    return AssembledText(full_text=full_text, offsets=offsets)


def _resolve_metadata(
    char_start: int,
    char_end: int,
    offsets: List[Tuple[int, int, Optional[int], Optional[int], Optional[str]]],
) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Resolve page, slide, and section metadata for a character range.

    Uses the first source segment within range to determine metadata.

    Args:
        char_start: Start of character range.
        char_end: End of character range.
        offsets: Position index from _assemble_text.

    Returns:
        Tuple of (page_number, slide_number, section).
    """
    page: Optional[int] = None
    slide: Optional[int] = None
    section: Optional[str] = None

    for start, end, p, s, sec in offsets:
        if end > char_start and start < char_end:
            # This segment overlaps with the chunk
            if page is None and p is not None:
                page = p
            if slide is None and s is not None:
                slide = s
            if section is None and sec is not None:
                section = sec
            if page is not None and slide is not None and section is not None:
                break

    return page, slide, section


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #


class DocumentPipeline:
    """Orchestrates the document processing pipeline."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def process(
        self,
        db: Session,
        document: Document,
    ) -> Document:
        """Process a single document end-to-end.

        Steps:
          1. Validate source type
          2. Set status = PROCESSING
          3. Extract text from file on disk
          4. Normalize text
          5. Chunk text
          6. Store chunks in DB (replaces any previous chunks)
          7. Set status = READY (or FAILED)
          8. Log structured processing report

        Idempotent: re-running replaces old chunks cleanly.

        Args:
            db: Database session.
            document: Document to process (must already be uploaded to disk).

        Returns:
            The updated document.
        """
        start = time.time()

        try:
            # ── Phase 0: Validate ───────────────────────────────────────
            ext = document.extension.lower()
            try:
                extractor_fn = get_extractor(ext)
            except ValueError as exc:
                return self._fail(
                    db, document, str(exc), start, "validation_error"
                )

            # ── Phase 1: Mark PROCESSING ─────────────────────────────────
            document.status = DocumentStatus.PROCESSING
            document.error_message = None
            db.commit()

            # ── Phase 2: Extract ─────────────────────────────────────────
            extract_start = time.time()
            filepath = Path(self.settings.UPLOAD_ROOT) / document.storage_key
            if not filepath.exists():
                return self._fail(
                    db,
                    document,
                    f"File not found at {document.storage_key}",
                    start,
                    "file_not_found",
                )

            try:
                results = extractor_fn(
                    filepath,
                    max_pages=self.settings.PDF_MAX_PAGES,
                )
            except ValueError as exc:
                return self._fail(
                    db, document, str(exc), start, "extraction_error"
                )

            extraction_time = time.time() - extract_start

            # ── Phase 3: Assemble & Normalize ────────────────────────────
            assembled = _assemble_text(results)
            full_text = assembled.full_text
            offsets = assembled.offsets

            if not full_text:
                # No extractable text — still mark as processed (0 chunks)
                document.status = DocumentStatus.READY
                document.error_message = None
                db.commit()
                self._log_report(
                    document=document,
                    outcome="success",
                    extraction_time=time.time() - extract_start,
                    chunking_time=0.0,
                    db_time=0.0,
                    total_time=time.time() - start,
                    char_count=0,
                    chunk_count=0,
                    failure_reason=None,
                    warnings=["no_extractable_text"],
                )
                return document

            # ── Phase 4: Chunk ───────────────────────────────────────────
            chunk_start = time.time()
            chunking_report = chunk_text(
                full_text,
                chunk_size=self.settings.CHUNK_SIZE,
                overlap=self.settings.CHUNK_OVERLAP,
            )
            chunking_time = time.time() - chunk_start

            if chunking_report.chunk_count == 0:
                # Text too short to produce chunks — still valid
                document.status = DocumentStatus.READY
                document.error_message = None
                db.commit()
                self._log_report(
                    document=document,
                    outcome="success",
                    extraction_time=time.time() - extract_start,
                    chunking_time=time.time() - chunk_start,
                    db_time=0.0,
                    total_time=time.time() - start,
                    char_count=len(full_text),
                    chunk_count=0,
                    failure_reason=None,
                    warnings=["no_chunks_generated"],
                )
                return document

            # ── Phase 5: Store chunks (idempotent) ───────────────────────
            db_start = time.time()

            # Delete any existing chunks for this document
            db.query(Chunk).filter(
                Chunk.document_id == document.id
            ).delete()

            for chunk in chunking_report.chunks:
                page, slide, section = _resolve_metadata(
                    chunk.character_start,
                    chunk.character_end,
                    offsets,
                )

                chunk_record = Chunk(
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    source_type=ext,
                    page_number=page or chunk.page_number,
                    slide_number=slide or chunk.slide_number,
                    section=section or chunk.section,
                    character_start=chunk.character_start,
                    character_end=chunk.character_end,
                    token_estimate=chunk.token_estimate,
                )
                db.add(chunk_record)

            # ── Phase 6: Mark READY ──────────────────────────────────
            document.status = DocumentStatus.READY
            document.error_message = None
            db.commit()

            db_time = time.time() - db_start
            total_time = time.time() - start

            # ── Phase 7: Log processing report ───────────────────────────
            self._log_report(
                document=document,
                outcome="success",
                extraction_time=extraction_time,
                chunking_time=chunking_time,
                db_time=db_time,
                total_time=total_time,
                char_count=len(full_text),
                chunk_count=chunking_report.chunk_count,
                failure_reason=None,
                warnings=None,
            )

            return document

        except Exception as exc:
            db.rollback()
            return self._fail(
                db,
                document,
                f"Unexpected processing error: {exc}",
                start,
                "unexpected_error",
            )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _fail(
        self,
        db: Session,
        document: Document,
        reason: str,
        start_time: float,
        error_code: str,
    ) -> Document:
        """Mark a document as failed with a structured error message."""
        try:
            # Clean up any partial chunks
            db.query(Chunk).filter(
                Chunk.document_id == document.id
            ).delete()

            document.status = DocumentStatus.FAILED
            document.error_message = reason
            db.commit()
        except Exception:
            db.rollback()

        total_time = time.time() - start_time
        self._log_report(
            document=document,
            outcome="failure",
            extraction_time=0.0,
            chunking_time=0.0,
            db_time=0.0,
            total_time=total_time,
            char_count=0,
            chunk_count=0,
            failure_reason=reason,
            warnings=[error_code],
        )

        return document

    def _log_report(
        self,
        document: Document,
        outcome: str,
        extraction_time: float,
        chunking_time: float,
        db_time: float,
        total_time: float,
        char_count: int,
        chunk_count: int,
        failure_reason: Optional[str] = None,
        warnings: Optional[List[str]] = None,
    ) -> None:
        """Emit a structured log entry for the processing result.

        Never logs document contents.
        """
        log_data = {
            "document_id": str(document.id),
            "user_id": str(document.user_id),
            "filename": document.filename,
            "extension": document.extension,
            "file_size_bytes": document.file_size,
            "outcome": outcome,
            "extraction_time_ms": round(extraction_time * 1000, 2),
            "chunking_time_ms": round(chunking_time * 1000, 2),
            "db_time_ms": round(db_time * 1000, 2),
            "total_time_ms": round(total_time * 1000, 2),
            "char_count": char_count,
            "chunk_count": chunk_count,
        }

        if failure_reason:
            log_data["failure_reason"] = failure_reason

        if warnings:
            log_data["warnings"] = warnings

        if outcome == "success":
            logger.info("pipeline.document_processed", **log_data)
        else:
            logger.warning("pipeline.document_processing_failed", **log_data)
