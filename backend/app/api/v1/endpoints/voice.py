"""REST endpoints for voice/audio features."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.services.audio_overview_service import generate_audio_overview

router = APIRouter(tags=["Voice"])


@router.post("/voice/overview")
def generate_overview(
    body: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Generate a two-speaker discussion script from selected documents."""
    document_ids = body.get("document_ids", [])
    parsed_ids = [UUID(d) for d in document_ids]
    result = generate_audio_overview(db, current_user.id, parsed_ids)
    return result
