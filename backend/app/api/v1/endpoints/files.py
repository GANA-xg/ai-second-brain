"""REST endpoints for the file upload system."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.upload import DocumentListResponse, DocumentResponse, UploadResponse
from app.services.file_service import FileService
from app.services.auth_logger import RequestContext

router = APIRouter(tags=["Files"])


def _build_upload_context(request: Request) -> RequestContext:
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else "unknown")
    )
    return RequestContext(
        request_id=getattr(request.state, "request_id", "unknown"),
        client_ip=client_ip,
        user_agent=request.headers.get("User-Agent", ""),
        endpoint=f"{request.method} {request.url.path}",
    )


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document file",
)
def upload_file(
    request: Request,
    file: UploadFile,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Upload a document file.

    Accepted formats: PDF, DOCX, PPTX, TXT, PNG, JPG, JPEG.
    Files are validated by extension, MIME content, size, and filename safety.
    """
    ctx = _build_upload_context(request)
    ctx.user_id = str(current_user.id)
    return FileService.upload(db, file, current_user.id, ctx=ctx)


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document metadata",
)
def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Retrieve metadata for a single document (ownership enforced)."""
    return FileService.get_document(db, document_id, current_user.id)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List user's documents",
)
def list_documents(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """List all documents owned by the authenticated user."""
    return FileService.list_documents(db, current_user.id, skip=skip, limit=limit)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a document",
)
def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a document by ID (ownership enforced)."""
    FileService.delete_document(db, document_id, current_user.id)
