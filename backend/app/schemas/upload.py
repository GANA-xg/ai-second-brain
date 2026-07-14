"""Pydantic schemas for the file upload system."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    """Public metadata for an uploaded document — no internal paths exposed."""

    id: UUID
    user_id: UUID
    original_filename: str
    mime_type: str
    extension: str
    file_size: int
    sha256_checksum: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    """Response returned after a successful upload."""

    message: str = "File uploaded successfully"
    document: DocumentResponse


class DocumentListResponse(BaseModel):
    """List of user documents with pagination info."""

    documents: list[DocumentResponse]
    total: int
