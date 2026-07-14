"""
Production-grade file upload service.

Handles validation, SHA-256 checksumming, filesystem storage, metadata
persistence, and status lifecycle for the document upload pipeline.

Storage layout:
  {UPLOAD_ROOT}/{user_id}/{document_id}/{original_filename}
"""
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, BinaryIO, List, Optional

import filetype
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.cache_keys import document_list_key
from app.services.cache_service import cache_service, invalidate_document_cache, invalidate_search_cache
from app.core.config import settings
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.schemas.upload import DocumentResponse, UploadResponse
from app.services.auth_logger import RequestContext
from app.services.vector_service import get_vector_service

# ---------------------------------------------------------------------------
# Allowed MIME types and their extensions
# ---------------------------------------------------------------------------
# Maps lowercase extension → (canonical extension, MIME type)
ALLOWED_TYPES: dict[str, tuple[str, str]] = {
    ".pdf":  (".pdf",  "application/pdf"),
    ".docx": (".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".pptx": (".pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ".txt":  (".txt",  "text/plain"),
    ".png":  (".png",  "image/png"),
    ".jpg":  (".jpg",  "image/jpeg"),
    ".jpeg": (".jpeg", "image/jpeg"),
}

ALLOWED_EXTENSIONS = set(ALLOWED_TYPES.keys())
ALLOWED_MIMES = {m for _, m in ALLOWED_TYPES.values()}

# ---------------------------------------------------------------------------
# Maximum safe path components to prevent deep nesting attacks
# ---------------------------------------------------------------------------
_MAX_FILENAME_LENGTH = 255
_TRAVERSAL_PATTERN = re.compile(
    r"(\.\./|\.\.\\|~|//|\\|[\x00-\x1f\x7f-\x9f])"
)


def _safe_filename(filename: str) -> str:
    """Validate and sanitize a filename, raising HTTPException on problems."""
    # ── Null bytes and control characters ──────────────────────────────
    if "\x00" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename contains null bytes",
        )
    if _TRAVERSAL_PATTERN.search(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename contains path traversal characters",
        )

    # ── Path separators (would create subdirectories) ────────────────
    if "/" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename must not contain path separators",
        )

    # ── Hidden files ──────────────────────────────────────────────────
    if filename.startswith("."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hidden files are not allowed",
        )

    # ── Length ────────────────────────────────────────────────────────
    if len(filename) > _MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Filename exceeds maximum length of {_MAX_FILENAME_LENGTH} characters",
        )

    return filename


def _validate_extension(filename: str) -> tuple[str, str]:
    """Validate the file extension and return (canonical_extension, mime_type)."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return ALLOWED_TYPES[ext]


def _validate_mime_type(file_obj: BinaryIO, expected_mime: str) -> None:
    """Validate the actual file content matches the expected MIME type."""
    # Read the beginning of the file for magic-bytes detection
    header = file_obj.read(2048)
    file_obj.seek(0)  # reset for checksumming

    if expected_mime == "text/plain":
        # Accept any non-binary content as text/plain
        if b"\x00" in header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File content is binary, but extension indicates text/plain",
            )
        return

    kind = filetype.guess(header)
    if kind is None or kind.mime != expected_mime:
        detected = kind.mime if kind else "unknown"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File content MIME type '{detected}' does not match expected '{expected_mime}'",
        )


def _calculate_sha256(file_obj: BinaryIO) -> str:
    """Compute SHA-256 checksum over the entire file content."""
    sha = hashlib.sha256()
    while chunk := file_obj.read(65536):
        sha.update(chunk)
    return sha.hexdigest()


def _store_file(
    upload_root: Path,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    original_filename: str,
    file_obj: BinaryIO,
) -> str:
    """Write the uploaded file to disk under ``upload_root/{user_id}/{document_id}/``.

    Returns the relative ``storage_key`` (the path stored in the DB).
    The API never reveals the absolute filesystem path.
    """
    dest_dir = upload_root / str(user_id) / str(document_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / original_filename

    # Defensive: should never collide since document_id is a new UUID
    if dest_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document ID collision on filesystem",
        )

    with open(dest_path, "wb") as f:
        while chunk := file_obj.read(65536):
            f.write(chunk)

    # Relative key stored in DB — never expose absolute paths
    return str(Path(str(user_id)) / str(document_id) / original_filename)


class FileService:
    """Business logic for file uploads."""

    @staticmethod
    def validate_upload(file: UploadFile) -> tuple[str, str, int]:
        """Validate an uploaded file.

        Returns ``(safe_filename, canonical_extension, size_bytes)``.
        Raises ``HTTPException`` on any validation failure.
        """
        # ── Filename ───────────────────────────────────────────────────
        raw_name = file.filename or ""
        safe_name = _safe_filename(raw_name)

        # ── Extension ──────────────────────────────────────────────────
        ext, expected_mime = _validate_extension(safe_name)

        # ── Size ───────────────────────────────────────────────────────
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)

        if size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )
        if size > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds maximum upload size of {settings.MAX_UPLOAD_SIZE_MB} MB",
            )

        # ── MIME content validation ─────────────────────────────────────
        _validate_mime_type(file.file, expected_mime)
        file.file.seek(0)

        return safe_name, ext, size

    @staticmethod
    def upload(
        db: Session,
        file: UploadFile,
        current_user_id: uuid.UUID,
        ctx: Optional[RequestContext] = None,
    ) -> UploadResponse:
        """Process and persist an uploaded file.

        The full pipeline:
          1. Validate filename, extension, size, MIME type
          2. Compute SHA-256 checksum
          3. Write file to disk under ``storage/{user_id}/{document_id}/``
          4. Persist metadata to database (status = READY)

        Single DB commit ensures atomicity: if anything fails at any
        point the database is rolled back and any partial file is removed.
        """
        start = time.time()

        # ── Validate (no side effects) ─────────────────────────────────
        safe_name, ext, size = FileService.validate_upload(file)

        # ── Checksum (no side effects) ─────────────────────────────────
        sha256 = _calculate_sha256(file.file)
        file.file.seek(0)

        document_id = uuid.uuid4()

        # ── Write file to disk ─────────────────────────────────────────
        #    This creates the side-effect *first* so a subsequent DB
        #    failure is caught (and the file cleaned up) rather than
        #    leaving an orphan DB record.
        upload_root = Path(settings.UPLOAD_ROOT)
        try:
            storage_key = _store_file(
                upload_root,
                current_user_id,
                document_id,
                safe_name,
                file.file,
            )
        except Exception:
            latency = time.time() - start
            _log_event(ctx, document_id, safe_name, size, None, "failure", latency)
            raise

        # ── DB record (single commit = atomic) ─────────────────────────
        try:
            doc = Document(
                id=document_id,
                user_id=current_user_id,
                filename=safe_name,
                original_filename=safe_name,
                mime_type=ALLOWED_TYPES[ext][1],
                extension=ext.lstrip("."),
                file_size=size,
                storage_key=storage_key,
                sha256_checksum=sha256,
                status=DocumentStatus.UPLOADED,
            )
            db.add(doc)
            db.commit()
        except Exception:
            db.rollback()
            # Clean up the file we already wrote
            _cleanup_file(upload_root, current_user_id, document_id, safe_name)
            latency = time.time() - start
            _log_event(ctx, document_id, safe_name, size, None, "failure", latency)
            raise

        latency = time.time() - start
        _log_event(ctx, document_id, safe_name, size, sha256, "success", latency)

        # ── Invalidate cached document list for the user ─────────────────────
        invalidate_document_cache(current_user_id)
        # Search results are also stale when new documents are uploaded
        invalidate_search_cache(current_user_id)

        # ── Trigger processing pipeline ───────────────────────────
        pipeline_failed = False
        try:
            from app.services.processing_pipeline import DocumentPipeline

            pipeline = DocumentPipeline(settings)
            doc = pipeline.process(db, doc)
        except Exception as pipe_exc:
            logger = get_logger("upload")
            logger.error(
                "upload.pipeline_failed",
                document_id=str(document_id),
                filename=safe_name,
                error=str(pipe_exc)[:500],
            )
            pipeline_failed = True

        # ── Trigger embedding pipeline (only if processing succeeded) ──
        if not pipeline_failed and doc.status == DocumentStatus.READY:
            try:
                from app.services.embedding_pipeline import EmbeddingPipeline

                embed_pipeline = EmbeddingPipeline(settings)
                doc = embed_pipeline.process(db, doc)
            except Exception as embed_exc:
                # Embedding failure is logged but doesn't fail the upload
                # The document stays PROCESSED; embeddings can be regenerated
                logger = get_logger("upload")
                logger.error(
                    "upload.embedding_failed",
                    document_id=str(document_id),
                    filename=safe_name,
                    error=str(embed_exc)[:500],
                )

        return UploadResponse(document=DocumentResponse.model_validate(doc))

    @staticmethod
    def get_document(
        db: Session,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> DocumentResponse:
        """Retrieve a document's metadata, enforcing ownership."""
        doc = db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.deleted_at.is_(None),
        ).first()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        return DocumentResponse.model_validate(doc)

    @staticmethod
    def list_documents(
        db: Session,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        """List documents for a user, newest first, with caching."""
        # Generate cache key for the user's document list
        cache_key = document_list_key(user_id)

        # Try to get cached data
        cached_data = cache_service.get(cache_key)
        if cached_data is not None:
            # Cache hit: apply pagination to the cached list
            cached_docs = cached_data.get("documents", [])
            total = cached_data.get("total", 0)
            # Apply pagination
            paginated_docs = cached_docs[skip : skip + limit]
            return {
                "documents": [DocumentResponse.model_validate(doc) for doc in paginated_docs],
                "total": total,
            }

        # Cache miss: query the database
        query = db.query(Document).filter(
            Document.user_id == user_id,
            Document.deleted_at.is_(None),
        ).order_by(Document.created_at.desc())

        total = query.count()
        docs = query.offset(0).limit(None).all()  # Fetch all documents for caching

        # Prepare data for caching: convert each document to a dict
        docs_data = [DocumentResponse.model_validate(doc).model_dump() for doc in docs]
        data_to_cache = {
            "documents": docs_data,
            "total": total,
        }

        # Cache the data with TTL from settings
        cache_service.set(
            cache_key,
            data_to_cache,
            ttl=settings.CACHE_DOCUMENT_TTL,
        )

        # Apply pagination to the fresh data
        paginated_docs = docs_data[skip : skip + limit]
        return {
            "documents": [DocumentResponse.model_validate(doc) for doc in paginated_docs],
            "total": total,
        }

    @staticmethod
    def delete_document(
        db: Session,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Soft-delete a document (ownership enforced). Also deletes Qdrant vectors."""
        doc = db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.deleted_at.is_(None),
        ).first()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # Delete Qdrant vectors for this document
        try:
            vector_service = get_vector_service()
            vector_service.delete_by_document(user_id=user_id, document_id=document_id)
        except Exception as exc:
            # Log but don't fail the deletion - document can be manually cleaned up later
            from app.core.logging import get_logger
            logger = get_logger("vector_delete")
            logger.warning(
                "vector.delete_failed_on_document_delete",
                document_id=str(document_id),
                user_id=str(user_id),
                error=str(exc)[:200],
            )

        doc.deleted_at = datetime.now(timezone.utc)
        doc.status = DocumentStatus.DELETED
        db.commit()

        # Invalidate cached document list for the user
        invalidate_document_cache(user_id)
        # Search results are also stale when documents are deleted
        invalidate_search_cache(user_id)


def _cleanup_file(
    upload_root: Path,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    filename: str,
) -> None:
    """Remove a partially-written file and its empty parent directories."""
    dest_dir = upload_root / str(user_id) / str(document_id)
    dest_path = dest_dir / filename
    try:
        if dest_path.exists():
            dest_path.unlink()
        if dest_dir.exists():
            dest_dir.rmdir()  # removes empty dir
        if dest_dir.parent.exists():
            dest_dir.parent.rmdir()  # removes user dir if empty
    except OSError:
        pass  # directory not empty or already removed — harmless


def _log_event(
    ctx: Optional[RequestContext],
    document_id: uuid.UUID,
    filename: str,
    size: int,
    checksum: Optional[str],
    outcome: str,
    latency: float,
) -> None:
    """Emit a structured log entry for the upload event."""
    if ctx is None:
        return
    from app.core.logging import get_logger

    logger = get_logger("upload")
    log_data = {
        "document_id": str(document_id),
        "filename": filename,
        "size_bytes": size,
        "outcome": outcome,
        "latency_ms": round(latency * 1000, 2),
        "request_id": ctx.request_id,
        "client_ip": ctx.client_ip,
        "user_agent": ctx.user_agent,
        "endpoint": ctx.endpoint,
    }
    if ctx.user_id:
        log_data["user_id"] = ctx.user_id
    if checksum:
        log_data["sha256"] = checksum

    if outcome == "success":
        logger.info("upload.file_uploaded", **log_data)
    else:
        logger.warning("upload.file_upload_failed", **log_data)
