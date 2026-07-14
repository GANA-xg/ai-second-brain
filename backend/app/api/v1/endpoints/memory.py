"""Memory management API endpoints.

Allows users to manage their long-term memories with full CRUD,
ownership enforcement, and soft-delete semantics.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.models.memory import MemoryType
from app.schemas.memory import (
    MemoryCreate,
    MemoryDeleteResponse,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdate,
)
from app.services.memory_service import (
    create_memory,
    get_memory,
    list_memories,
    update_memory,
    soft_delete_memory,
    bulk_delete_memories,
)

router = APIRouter(tags=["Memories"])


@router.get("", response_model=MemoryListResponse)
def get_memories(
    memory_type: Optional[MemoryType] = Query(None, alias="type"),
    is_active: Optional[bool] = Query(None),
    include_deleted: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List memories for the authenticated user.

    Supports filtering by type, active status, and pagination.
    """
    memories, total = list_memories(
        db,
        current_user.id,
        memory_type=memory_type,
        is_active=is_active,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )
    return MemoryListResponse(
        memories=[MemoryResponse.model_validate(m) for m in memories],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )


@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_memory_endpoint(
    body: MemoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new memory manually.

    If a duplicate (by normalised content + type) already exists,
    the existing memory is returned with its timestamp updated.
    """
    mem = create_memory(
        db,
        current_user.id,
        content=body.content,
        memory_type=body.type,  # type: ignore[arg-type]  # schema/model enums share values
        confidence=body.confidence,
    )
    return MemoryResponse.model_validate(mem)


@router.get("/{memory_id}", response_model=MemoryResponse)
def get_memory_endpoint(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single memory by ID."""
    mem = get_memory(db, memory_id, current_user.id)
    if mem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return MemoryResponse.model_validate(mem)


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory_endpoint(
    memory_id: uuid.UUID,
    body: MemoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a memory's content, type, or active status."""
    mem = update_memory(db, memory_id, current_user.id, body)
    if mem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return MemoryResponse.model_validate(mem)


@router.delete("/{memory_id}", response_model=MemoryDeleteResponse)
def delete_memory_endpoint(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a single memory."""
    deleted = soft_delete_memory(db, memory_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return MemoryDeleteResponse(
        detail="Memory deleted",
        deleted_count=1,
    )


@router.delete("", response_model=MemoryDeleteResponse)
def delete_all_memories_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete ALL memories for the current user ('Forget Everything')."""
    count = bulk_delete_memories(db, current_user.id)
    return MemoryDeleteResponse(
        detail=f"Deleted {count} memories",
        deleted_count=count,
    )
