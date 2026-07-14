"""REST endpoints for the flashcard system."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.flashcard import (
    FlashcardDeleteResponse,
    FlashcardGenerateResponse,
    FlashcardListResponse,
    FlashcardResponse,
    FlashcardUpdate,
)
from app.services.flashcard_service import (
    delete_document_flashcards,
    delete_flashcard,
    generate_flashcards,
    list_flashcards,
    update_flashcard,
)

router = APIRouter(tags=["Flashcards"])


@router.post(
    "/documents/{document_id}/flashcards/generate",
    response_model=FlashcardGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate flashcards from a document",
)
def generate_document_flashcards(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Generate flashcards from all chunks of a document using Gemini.

    Chunks are batched and each batch is sent to Gemini. Valid flashcards
    are stored with provenance back to their source chunk.
    """
    result = generate_flashcards(db, current_user.id, document_id)
    return FlashcardGenerateResponse(
        message=result["message"],
        generated_count=result["generated_count"],
        discarded_count=result["discarded_count"],
        total_count=result["total_count"],
    )


@router.get(
    "/flashcards",
    response_model=FlashcardListResponse,
    summary="List flashcards",
)
def list_user_flashcards(
    document_id: UUID | None = Query(
        None, description="Filter by document ID",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(
        20, ge=1, le=100, description="Items per page",
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List flashcards for the authenticated user.

    Supports optional filtering by document_id and pagination.
    """
    return list_flashcards(
        db,
        current_user.id,
        document_id=document_id,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/flashcards/{flashcard_id}",
    response_model=FlashcardResponse,
    summary="Update a flashcard",
)
def update_user_flashcard(
    flashcard_id: UUID,
    update_data: FlashcardUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update a flashcard's front and/or back text. Ownership required."""
    card = update_flashcard(
        db,
        current_user.id,
        flashcard_id,
        front=update_data.front,
        back=update_data.back,
    )
    return card


@router.delete(
    "/flashcards/{flashcard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a flashcard",
)
def delete_user_flashcard(
    flashcard_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a flashcard. Ownership required."""
    delete_flashcard(db, current_user.id, flashcard_id)


@router.delete(
    "/documents/{document_id}/flashcards",
    response_model=FlashcardDeleteResponse,
    summary="Delete all flashcards for a document",
)
def delete_document_flashcards_endpoint(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Soft-delete all flashcards belonging to a document. Ownership required."""
    count = delete_document_flashcards(db, current_user.id, document_id)
    return FlashcardDeleteResponse(
        detail=f"Deleted {count} flashcards",
        deleted_count=count,
    )
