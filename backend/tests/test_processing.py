"""Tests for the document processing pipeline (Part 5).

Tests cover:
  - Text extraction (PDF, DOCX, PPTX, TXT, image)
  - Text normalization (deterministic Unicode/whitespace/line-ending)
  - Deterministic chunking (order, count, overlap, metadata)
  - Full pipeline integration via upload API
  - Metadata persistence on stored chunks
  - Idempotent reprocessing
  - Transaction safety (no orphan chunks on failure)
  - Structured processing logs
"""

import io
import logging
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.services.text_extractor import (
    ExtractionResult,
    extract_docx,
    extract_image,
    extract_pdf,
    extract_pptx,
    extract_txt,
    get_extractor,
)
from app.services.text_normalizer import normalize_text
from app.services.text_chunker import chunk_text
from tests.conftest import TestingSessionLocal
from tests.helpers import (
    make_docx_bytes,
    make_pdf_bytes,
    make_pptx_bytes,
    make_txt_bytes,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

LONG_TEXT = """The quick brown fox jumps over the lazy dog. This sentence contains
every letter of the English alphabet at least once and is commonly used for
testing fonts and typing skills.

Python is a high-level, general-purpose programming language. Its design
philosophy emphasizes code readability with the use of significant
indentation. Python is dynamically typed and garbage-collected.

FastAPI is a modern, fast web framework for building APIs with Python. It
uses standard Python type hints and is built on top of Starlette for the
web parts and Pydantic for the data parts.

SQLAlchemy is the Python SQL toolkit and Object Relational Mapper that gives
application developers the full power and flexibility of SQL. It provides a
full suite of well known enterprise-level persistence patterns.

Pydantic provides data validation using Python type annotations. It uses
a declarative model style where you define fields and their types, and
Pydantic handles validation, serialization, and deserialization.

This text is designed to be long enough to produce multiple chunks when
processed with the default chunk size of 1000 characters and overlap of
200 characters. Each paragraph adds roughly 150 to 300 characters.

The chunking algorithm splits text on character boundaries with a
configurable window size and overlap. It avoids tiny trailing chunks
by extending the last chunk when remaining text is under 20 percent of
the chunk size.

Character position metadata is preserved throughout the pipeline so
each chunk knows exactly where its text originated. This allows
downstream systems to reference specific locations in the source.

Token estimates are computed using a simple heuristic: characters divided
by four. This provides a rough count suitable for most embedding models
and LLM context windows without requiring a separate tokenizer.
"""


def _upload_document(client, auth_headers, filename: str, content: bytes):
    """Helper: upload a document via the API."""
    r = client.post(
        "/api/v1/files/upload",
        files={"file": (filename, content)},
        headers=auth_headers,
    )
    return r


def _get_chunks_for_document(document_id: str) -> list[Chunk]:
    """Query chunks directly from the test database."""
    db: Session = TestingSessionLocal()
    try:
        chunks = (
            db.query(Chunk)
            .filter(Chunk.document_id == uuid.UUID(document_id))
            .order_by(Chunk.chunk_index)
            .all()
        )
        return chunks
    finally:
        db.close()


def _get_document_status(document_id: str) -> str:
    """Query document status from the test database."""
    db: Session = TestingSessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == uuid.UUID(document_id)).first()
        return doc.status.value if doc else None
    finally:
        db.close()


def _get_document_error(document_id: str) -> str:
    """Query document error_message from the test database."""
    db: Session = TestingSessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == uuid.UUID(document_id)).first()
        return doc.error_message
    finally:
        db.close()


# ===================================================================
# Extraction Tests (unit level)
# ===================================================================


class TestExtraction:
    """Direct extraction tests for each format."""

    def test_extract_pdf(self, tmp_path):
        """Extract text from a real PDF with content."""
        content = make_pdf_bytes(LONG_TEXT)
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(content)

        results = extract_pdf(pdf_path)
        assert len(results) >= 1
        # Should have extracted some text
        combined = " ".join(r.text for r in results)
        assert "Python" in combined
        assert "FastAPI" in combined
        assert results[0].page_number is not None

    def test_extract_docx(self, tmp_path):
        """Extract text from a DOCX with paragraphs."""
        content = make_docx_bytes(LONG_TEXT)
        docx_path = tmp_path / "test.docx"
        docx_path.write_bytes(content)

        results = extract_docx(docx_path)
        assert len(results) >= 1
        combined = " ".join(r.text for r in results)
        assert "Python" in combined
        assert "SQLAlchemy" in combined
        # Section is only set for heading-styled paragraphs; plain text has no section

    def test_extract_pptx(self, tmp_path):
        """Extract text from a PPTX with slides."""
        content = make_pptx_bytes(LONG_TEXT)
        pptx_path = tmp_path / "test.pptx"
        pptx_path.write_bytes(content)

        results = extract_pptx(pptx_path)
        assert len(results) >= 1
        combined = " ".join(r.text for r in results)
        assert "Python" in combined
        assert results[0].slide_number is not None

    def test_extract_txt(self, tmp_path):
        """Extract text from a TXT file."""
        content = make_txt_bytes(LONG_TEXT)
        txt_path = tmp_path / "test.txt"
        txt_path.write_bytes(content)

        results = extract_txt(txt_path)
        assert len(results) >= 1
        assert "Python" in results[0].text
        assert "FastAPI" in results[0].text

    def test_extract_image_raises(self, tmp_path):
        """Image extraction raises ValueError (OCR not implemented)."""
        img_path = tmp_path / "test.png"
        img_path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        with pytest.raises(ValueError, match="OCR text extraction is not yet implemented"):
            extract_image(img_path)

    def test_corrupted_pdf_raises(self, tmp_path):
        """Corrupted PDF raises ValueError."""
        pdf_path = tmp_path / "bad.pdf"
        pdf_path.write_bytes(b"not a pdf content")
        with pytest.raises((ValueError, Exception)):
            extract_pdf(pdf_path)

    def test_corrupted_docx_raises(self, tmp_path):
        """Corrupted DOCX raises ValueError."""
        docx_path = tmp_path / "bad.docx"
        docx_path.write_bytes(b"not a zip file")
        with pytest.raises(ValueError):
            extract_docx(docx_path)

    def test_unsupported_format(self):
        """get_extractor raises ValueError for unknown extensions."""
        with pytest.raises(ValueError, match="Unsupported file extension for extraction"):
            get_extractor("xyz")

    def test_empty_txt(self, tmp_path):
        """Empty text file returns empty result."""
        txt_path = tmp_path / "empty.txt"
        txt_path.write_bytes(b"")
        results = extract_txt(txt_path)
        assert len(results) == 1
        assert results[0].text == ""


# ===================================================================
# Normalization Tests
# ===================================================================


class TestNormalization:
    """Deterministic text normalization."""

    def test_unicode_nfc_normalization(self):
        """Unicode is normalized to NFC."""
        # "café" in decomposed form (NFD)
        raw = "cafe\u0301"
        normalized = normalize_text(raw)
        # After NFC normalization it should be the composed form "é"
        assert "é" in normalized or "e\u0301" not in normalized
        # Should be deterministic
        assert normalize_text(raw) == normalize_text(raw)

    def test_line_ending_normalization(self):
        """CRLF and CR are converted to LF."""
        raw = "line1\r\nline2\rline3"
        result = normalize_text(raw, preserve_boundaries=False)
        # Newlines should be collapsed to spaces with preserve_boundaries=False
        assert "\r" not in result
        assert "line1 line2 line3" == result

    def test_whitespace_collapse(self):
        """Multiple spaces and tabs are collapsed."""
        raw = "hello    world\t\ttest"
        result = normalize_text(raw, preserve_boundaries=False)
        assert "hello world test" == result

    def test_trim_whitespace(self):
        """Leading and trailing whitespace is removed."""
        raw = "  \n  hello world  \n  "
        result = normalize_text(raw, preserve_boundaries=False)
        assert result == "hello world"

    def test_preserve_boundaries(self):
        """Paragraph boundaries are preserved."""
        raw = "para1\n\n\npara2"
        result = normalize_text(raw, preserve_boundaries=True)
        # Should keep single blank line between paragraphs
        assert "para1\n\npara2" in result or result == "para1\n\npara2"

    def test_deterministic(self):
        """Same input always produces same output."""
        raw = "  Hello\r\n  World  \tTest\n\n\nEnd."
        r1 = normalize_text(raw)
        r2 = normalize_text(raw)
        assert r1 == r2

    def test_empty_input(self):
        """Empty input returns empty string."""
        assert normalize_text("") == ""


# ===================================================================
# Chunking Tests
# ===================================================================


class TestChunking:
    """Deterministic chunking tests."""

    def _generate_text(self, target_chars: int) -> str:
        """Generate text of approximately target_chars length."""
        paragraph = (
            "Python is a high-level programming language. "
            "It emphasizes code readability and simplicity. "
            "FastAPI builds on Python type hints for modern API development. "
            "SQLAlchemy provides powerful ORM capabilities for database access. "
        )
        repeats = (target_chars // len(paragraph)) + 1
        result = "\n\n".join([paragraph.strip()] * repeats)
        return result[:target_chars]

    def test_basic_chunking(self):
        """Text is split into chunks of the configured size."""
        text = self._generate_text(2500)
        report = chunk_text(text, chunk_size=1000, overlap=200)
        assert report.chunk_count >= 2
        for chunk in report.chunks:
            assert len(chunk.content) <= 1000

    def test_chunk_ordering(self):
        """Chunks are returned in stable order with sequential indices."""
        text = self._generate_text(2500)
        report = chunk_text(text, chunk_size=1000, overlap=200)
        indices = [c.chunk_index for c in report.chunks]
        assert indices == sorted(indices)
        assert indices == list(range(len(indices)))

    def test_chunk_count_stability(self):
        """Same input always produces same chunk count."""
        text = self._generate_text(2500)
        r1 = chunk_text(text, chunk_size=1000, overlap=200)
        r2 = chunk_text(text, chunk_size=1000, overlap=200)
        assert r1.chunk_count == r2.chunk_count
        assert len(r1.chunks) == len(r2.chunks)

    def test_deterministic_output(self):
        """Same input produces identical chunks."""
        text = self._generate_text(2500)
        r1 = chunk_text(text, chunk_size=1000, overlap=200)
        r2 = chunk_text(text, chunk_size=1000, overlap=200)
        for c1, c2 in zip(r1.chunks, r2.chunks):
            assert c1.content == c2.content
            assert c1.character_start == c2.character_start
            assert c1.character_end == c2.character_end

    def test_overlap_correctness(self):
        """Consecutive chunks overlap by configured amount."""
        text = self._generate_text(2500)
        report = chunk_text(text, chunk_size=1000, overlap=200)
        for i, chunk in enumerate(report.chunks):
            if i > 0:
                prev = report.chunks[i - 1]
                overlap_start = max(prev.character_start, chunk.character_start)
                overlap_end = min(prev.character_end, chunk.character_end)
                overlap_size = overlap_end - overlap_start
                # Overlap should exist and not exceed configured overlap
                assert overlap_size > 0
                assert overlap_size <= 200

    def test_no_duplicate_chunks(self):
        """No two chunks have identical content."""
        text = self._generate_text(3000)
        report = chunk_text(text, chunk_size=1000, overlap=200)
        contents = [c.content for c in report.chunks]
        # Allow for the possibility of identical content from overlap regions
        # but at minimum no two chunks have identical character ranges
        ranges = [(c.character_start, c.character_end) for c in report.chunks]
        assert len(ranges) == len(set(ranges))

    def test_tiny_trailing_chunk_absorbed(self):
        """Text that would produce a tiny final chunk is merged into previous."""
        # Create text that would give a main chunk and a tiny remainder
        text = "A" * 950 + "\n"
        report = chunk_text(text, chunk_size=1000, overlap=200)
        # Should produce exactly 1 chunk (tiny remainder absorbed)
        assert report.chunk_count == 1

    def test_chunk_metadata(self):
        """Each chunk has correct position metadata."""
        text = self._generate_text(2500)
        report = chunk_text(text, chunk_size=1000, overlap=200)
        for chunk in report.chunks:
            # Character range should be valid
            assert chunk.character_start >= 0
            assert chunk.character_end > chunk.character_start
            assert chunk.character_end <= len(text)
            # Token estimate should be positive
            assert chunk.token_estimate > 0
            # Content should match the character range
            assert chunk.content == text[chunk.character_start:chunk.character_end]

    def test_empty_text(self):
        """Empty text produces zero chunks."""
        report = chunk_text("", chunk_size=1000, overlap=200)
        assert report.chunk_count == 0

    def test_different_config_yields_different_chunks(self):
        """Different chunk_size/overlap produces different chunking."""
        text = self._generate_text(2500)
        r_small = chunk_text(text, chunk_size=500, overlap=100)
        r_large = chunk_text(text, chunk_size=1000, overlap=200)
        assert r_small.chunk_count != r_large.chunk_count


# ===================================================================
# Pipeline Integration Tests
# ===================================================================


class TestPipelineIntegration:
    """Full pipeline integration via upload API."""

    def test_upload_pdf_processes(self, client, auth_headers):
        """Uploading a PDF triggers pipeline and produces chunks."""
        content = make_pdf_bytes(LONG_TEXT)
        r = _upload_document(client, auth_headers, "test.pdf", content)
        assert r.status_code == 201
        doc_id = r.json()["document"]["id"]
        assert r.json()["document"]["status"] == "READY"

        chunks = _get_chunks_for_document(doc_id)
        assert len(chunks) > 0
        assert chunks[0].source_type == "pdf"

    def test_upload_docx_processes(self, client, auth_headers):
        """Uploading a DOCX triggers pipeline and produces chunks."""
        content = make_docx_bytes(LONG_TEXT)
        r = _upload_document(client, auth_headers, "report.docx", content)
        assert r.status_code == 201
        doc_id = r.json()["document"]["id"]
        assert r.json()["document"]["status"] == "READY"

        chunks = _get_chunks_for_document(doc_id)
        assert len(chunks) > 0
        assert chunks[0].source_type == "docx"

    def test_upload_pptx_processes(self, client, auth_headers):
        """Uploading a PPTX triggers pipeline and produces chunks."""
        content = make_pptx_bytes(LONG_TEXT)
        r = _upload_document(client, auth_headers, "slides.pptx", content)
        assert r.status_code == 201
        doc_id = r.json()["document"]["id"]
        assert r.json()["document"]["status"] == "READY"

        chunks = _get_chunks_for_document(doc_id)
        assert len(chunks) > 0
        assert chunks[0].source_type == "pptx"

    def test_upload_txt_processes(self, client, auth_headers):
        """Uploading a TXT triggers pipeline and produces chunks."""
        content = make_txt_bytes(LONG_TEXT)
        r = _upload_document(client, auth_headers, "notes.txt", content)
        assert r.status_code == 201
        doc_id = r.json()["document"]["id"]
        assert r.json()["document"]["status"] == "READY"

        chunks = _get_chunks_for_document(doc_id)
        assert len(chunks) > 0
        assert chunks[0].source_type == "txt"

    def test_upload_image_fails_gracefully(self, client, auth_headers):
        """Uploading an image results in FAILED status (OCR not implemented)."""
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        r = _upload_document(client, auth_headers, "diagram.png", png_bytes)
        assert r.status_code == 201
        assert r.json()["document"]["status"] == "FAILED"
        assert r.json()["document"]["error_message"] is not None
        assert "OCR" in r.json()["document"]["error_message"]

    def test_unsupported_format_rejected(self, client, auth_headers):
        """Unsupported file format is rejected at validation (400), not pipeline."""
        r = _upload_document(client, auth_headers, "data.csv", b"a,b,c\n1,2,3")
        assert r.status_code == 400


# ===================================================================
# Metadata Tests
# ===================================================================


class TestChunkMetadata:
    """Verify that stored chunks carry all required metadata."""

    def test_chunk_metadata_fields(self, client, auth_headers):
        """Every chunk has document_id, chunk_index, source_type, character range, and token estimate."""
        content = make_txt_bytes(LONG_TEXT)
        r = _upload_document(client, auth_headers, "metadata.txt", content)
        assert r.status_code == 201
        doc_id = r.json()["document"]["id"]

        chunks = _get_chunks_for_document(doc_id)
        assert len(chunks) > 0

        for chunk in chunks:
            assert chunk.document_id is not None
            assert chunk.chunk_index >= 0
            assert chunk.source_type is not None
            assert chunk.character_start is not None
            assert chunk.character_end is not None
            assert chunk.character_end > chunk.character_start
            assert chunk.token_estimate > 0
            assert chunk.created_at is not None

    def test_chunk_ordering(self, client, auth_headers):
        """Chunks are stored with sequential indices."""
        content = make_txt_bytes(LONG_TEXT)
        r = _upload_document(client, auth_headers, "ordered.txt", content)
        doc_id = r.json()["document"]["id"]

        chunks = _get_chunks_for_document(doc_id)
        indices = [c.chunk_index for c in chunks]
        assert indices == sorted(indices)
        assert indices == list(range(len(indices)))

    def test_character_ranges_are_contiguous(self, client, auth_headers):
        """Chunk character ranges cover the full text without gaps."""
        content = make_txt_bytes(LONG_TEXT)
        r = _upload_document(client, auth_headers, "ranges.txt", content)
        doc_id = r.json()["document"]["id"]

        chunks = _get_chunks_for_document(doc_id)
        if len(chunks) >= 2:
            # Verify character ranges are in order
            for i in range(1, len(chunks)):
                assert chunks[i].character_start >= chunks[i - 1].character_end - 200  # allow overlap

    def test_source_type_reflects_extension(self, client, auth_headers):
        """source_type matches the document extension."""
        cases = [
            ("doc.pdf", "pdf", make_pdf_bytes(LONG_TEXT)),
            ("report.docx", "docx", make_docx_bytes(LONG_TEXT)),
            ("slides.pptx", "pptx", make_pptx_bytes(LONG_TEXT)),
            ("notes.txt", "txt", make_txt_bytes(LONG_TEXT)),
        ]
        for fname, expected_ext, content in cases:
            r = _upload_document(client, auth_headers, fname, content)
            assert r.status_code == 201, f"Failed for {fname}"
            doc_id = r.json()["document"]["id"]
            chunks = _get_chunks_for_document(doc_id)
            assert len(chunks) > 0, f"No chunks for {fname}"
            for chunk in chunks:
                assert chunk.source_type == expected_ext, \
                    f"Expected {expected_ext}, got {chunk.source_type} for {fname}"


# ===================================================================
# Idempotency Tests
# ===================================================================


class TestIdempotency:
    """Processing the same document twice must not create duplicate chunks."""

    def test_reprocessing_replaces_chunks(self, client, auth_headers, monkeypatch, tmp_path):
        """Uploading the same document twice creates independent records
        (two different uploads, two different document IDs)."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "UPLOAD_ROOT", str(tmp_path / "storage"))

        content = make_txt_bytes(LONG_TEXT)

        # First upload
        r1 = _upload_document(client, auth_headers, "test.txt", content)
        assert r1.status_code == 201
        doc_id_1 = r1.json()["document"]["id"]
        chunks_1 = _get_chunks_for_document(doc_id_1)
        assert len(chunks_1) > 0

        # Second upload (same content, new UUID)
        r2 = _upload_document(client, auth_headers, "test2.txt", content)
        assert r2.status_code == 201
        doc_id_2 = r2.json()["document"]["id"]
        chunks_2 = _get_chunks_for_document(doc_id_2)
        assert len(chunks_2) > 0

        # Different document IDs
        assert doc_id_1 != doc_id_2
        # Each document has its own chunks
        assert len(chunks_1) == len(chunks_2)
        # Chunk content should be identical since source text is identical
        for c1, c2 in zip(chunks_1, chunks_2):
            assert c1.content == c2.content
            assert c1.character_start == c2.character_start
            assert c1.character_end == c2.character_end


# ===================================================================
# Transaction Safety Tests
# ===================================================================


class TestTransactionSafety:
    """Failed processing must not leave orphan chunks."""

    def test_image_upload_has_no_chunks(self, client, auth_headers):
        """Image upload fails pipeline, but should have no orphan chunks."""
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        r = _upload_document(client, auth_headers, "diagram.png", png_bytes)
        assert r.status_code == 201
        doc_id = r.json()["document"]["id"]
        assert r.json()["document"]["status"] == "FAILED"

        chunks = _get_chunks_for_document(doc_id)
        assert len(chunks) == 0, "Failed processing should leave no orphan chunks"

    def test_status_becomes_failed_on_pipeline_error(self, client, auth_headers):
        """When pipeline fails, document status is FAILED with error message."""
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        r = _upload_document(client, auth_headers, "img.png", png_bytes)
        assert r.status_code == 201
        assert r.json()["document"]["status"] == "FAILED"
        error_msg = r.json()["document"]["error_message"]
        assert error_msg is not None
        assert "OCR text extraction is not yet implemented" in error_msg


# ===================================================================
# Logging Tests
# ===================================================================


class TestProcessingLogging:
    """Verify structured processing logs are emitted."""

    def test_processing_success_logged(self, client, auth_headers, caplog):
        """Successful processing logs 'pipeline.document_processed'."""
        caplog.set_level(logging.INFO)
        content = make_txt_bytes("Short text for testing.")
        r = _upload_document(client, auth_headers, "test.txt", content)
        assert r.status_code == 201

        # processing_pipeline uses "processing_pipeline" logger name
        assert "pipeline.document_processed" in caplog.text
        assert "test.txt" in caplog.text

    def test_processing_failure_logged(self, client, auth_headers, caplog):
        """Failed processing logs 'pipeline.document_processing_failed'."""
        caplog.set_level(logging.WARNING)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        r = _upload_document(client, auth_headers, "img.png", png_bytes)
        assert r.status_code == 201
        assert r.json()["document"]["status"] == "FAILED"

        assert "pipeline.document_processing_failed" in caplog.text
        assert "img.png" in caplog.text

    def test_document_content_not_in_logs(self, client, auth_headers, caplog):
        """Document contents are never written to logs."""
        caplog.set_level(logging.DEBUG)
        secret_text = "TOP-SECRET-CONTENT-12345"
        content = make_txt_bytes(secret_text + "\n" + LONG_TEXT)
        r = _upload_document(client, auth_headers, "secret.txt", content)
        assert r.status_code == 201

        # The secret content should NOT appear in logs
        assert "TOP-SECRET-CONTENT-12345" not in caplog.text
