"""Chat system API — conversation CRUD, messages, SSE streaming.

All business logic lives in the service layer; this file is pure HTTP routing.
"""

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db
from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.chat import (
    ChatErrorResponse,
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummary,
    ConversationUpdate,
    MessageResponse,
    PaginatedMessages,
    StreamEvent,
)
from app.services.conversation_service import (
    ConversationAccessDeniedError,
    ConversationNotFoundError,
    auto_title_from_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    update_conversation_title,
)
from app.services.message_service import (
    get_messages,
)
from app.services.rag_service import RAGError, answer_question, stream_answer

logger = get_logger("chat_api")

# ── Background memory extraction helper ────────────────────────────


def _run_background_memory_extraction(
    *,
    user_message: str,
    assistant_response: str,
    user_id: UUID,
    source_message_id: UUID,
) -> None:
    """Run memory extraction in a background task with its own DB session.

    Never raises — all failures are logged and swallowed so the
    background task never disrupts the chat response.
    """
    from app.db.session import SessionLocal
    from app.services.memory_extractor import extract_memories_from_exchange

    try:
        db = SessionLocal()
        try:
            extract_memories_from_exchange(
                user_message=user_message,
                assistant_response=assistant_response,
                user_id=user_id,
                source_message_id=source_message_id,
                db=db,
            )
        finally:
            db.close()
    except Exception:
        logger.exception("memory_extraction.background_crash")


router = APIRouter(prefix="/chat", tags=["chat"])


# ═══════════════════════════════════════════════════════════════════════
# Conversation CRUD
# ═══════════════════════════════════════════════════════════════════════


@router.post(
    "/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation_endpoint(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationSummary:
    """Create a new conversation with optional title."""
    conv = create_conversation(
        db=db,
        user_id=current_user.id,
        title=body.title,
    )
    return ConversationSummary(
        id=conv.id,
        title=conv.title,
        message_count=0,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
) -> ConversationListResponse:
    """List all conversations for the current user."""
    conversations, total = list_conversations(
        db=db,
        user_id=current_user.id,
        limit=min(limit, settings.MAX_PAGE_SIZE),
        offset=offset,
    )
    # Single aggregate query: O(1) instead of O(N)
    conv_ids = [c.id for c in conversations]
    msg_counts: dict[UUID, int] = {
        row[0]: row[1]
        for row in (
            db.query(Message.conversation_id, func.count(Message.id))
            .filter(Message.conversation_id.in_(conv_ids))
            .group_by(Message.conversation_id)
            .all()
        )
    }
    summaries = [
        ConversationSummary(
            id=conv.id,
            title=conv.title,
            message_count=msg_counts.get(conv.id, 0),
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )
        for conv in conversations
    ]
    return ConversationListResponse(conversations=summaries, total=total)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation_endpoint(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = 1,
    page_size: int = settings.DEFAULT_PAGE_SIZE,
) -> ConversationDetailResponse:
    """Get a conversation with paginated messages."""
    page_size = min(page_size, settings.MAX_PAGE_SIZE)
    try:
        conv = get_conversation(db, conversation_id, current_user.id)
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    except ConversationAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this conversation",
        )

    messages, total_messages, has_next = get_messages(
        db=db,
        conversation_id=conv.id,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )

    return ConversationDetailResponse(
        id=conv.id,
        title=conv.title,
        messages=[
            MessageResponse(
                id=msg.id,
                role=msg.role.value if hasattr(msg.role, "value") else str(msg.role),
                content=msg.content,
                status=msg.status.value if msg.status else None,
                citations=msg.citations,
                prompt_tokens=msg.prompt_tokens,
                completion_tokens=msg.completion_tokens,
                total_tokens=msg.total_tokens,
                error_metadata=msg.error_metadata,
                created_at=msg.created_at,
            )
            for msg in messages
        ],
        message_count=total_messages,
        page=page,
        page_size=page_size,
        has_next=has_next,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
def update_conversation_endpoint(
    conversation_id: UUID,
    body: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationSummary:
    """Rename a conversation."""
    try:
        conv = update_conversation_title(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user.id,
            new_title=body.title,
        )
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    except ConversationAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this conversation",
        )

    return ConversationSummary(
        id=conv.id,
        title=conv.title,
        message_count=(
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .count()
        ),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation_endpoint(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a conversation and all its messages."""
    try:
        delete_conversation(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user.id,
        )
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    except ConversationAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this conversation",
        )


# ═══════════════════════════════════════════════════════════════════════
# Messages
# ═══════════════════════════════════════════════════════════════════════


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=PaginatedMessages,
)
def get_messages_endpoint(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = 1,
    page_size: int = settings.DEFAULT_PAGE_SIZE,
) -> PaginatedMessages:
    """Get paginated messages for a conversation."""
    page_size = min(page_size, settings.MAX_PAGE_SIZE)
    try:
        messages, total, has_next = get_messages(
            db=db,
            conversation_id=conversation_id,
            user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
    except ConversationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    except ConversationAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this conversation",
        )

    return PaginatedMessages(
        messages=[
            MessageResponse(
                id=msg.id,
                role=msg.role.value if hasattr(msg.role, "value") else str(msg.role),
                content=msg.content,
                status=msg.status.value if msg.status else None,
                citations=msg.citations,
                prompt_tokens=msg.prompt_tokens,
                completion_tokens=msg.completion_tokens,
                total_tokens=msg.total_tokens,
                error_metadata=msg.error_metadata,
                created_at=msg.created_at,
            )
            for msg in messages
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )


# ═══════════════════════════════════════════════════════════════════════
# Legacy synchronous RAG endpoint
# ═══════════════════════════════════════════════════════════════════════


@router.post(
    "/ask",
    response_model=ChatResponse,
    responses={
        400: {"model": ChatErrorResponse},
        500: {"model": ChatErrorResponse},
    },
)
def ask_question(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """Ask a question against the user's uploaded documents.

    The RAG pipeline will:
      1. Embed the question
      2. Search Qdrant (user-scoped)
      3. Pack context
      4. Call Gemini
      5. Return grounded answer with citations

    After the response is sent, memory extraction runs in the background.
    """
    try:
        result = answer_question(
            db=db,
            user_id=current_user.id,
            question=request.question,
            conversation_id=request.conversation_id,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
        )
    except RAGError as e:
        logger.error(
            "chat.rag_error",
            user_id=str(current_user.id),
            error=str(e)[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "chat.internal_error",
            user_id=str(current_user.id),
            error=str(e)[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {str(e)[:200]}",
        )

    # Schedule background memory extraction after successful response
    if settings.ENABLE_AUTO_MEMORY:
        background_tasks.add_task(
            _run_background_memory_extraction,
            user_message=request.question,
            assistant_response=result.answer,
            user_id=current_user.id,
            source_message_id=result.message_id,
        )

    return result


# ═══════════════════════════════════════════════════════════════════════
# SSE Streaming Endpoint
# ═══════════════════════════════════════════════════════════════════════


@router.post("/stream", response_class=StreamingResponse)
async def stream_question(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream a grounded answer token-by-token via Server-Sent Events.

    The stream produces JSON events with `type` field:
      - "token": a text token from Gemini
      - "citation": the source citations (sent before the first token)
      - "done": stream complete, includes final citations and IDs
      - "error": an error occurred

    Flow:
      1. User message saved BEFORE any AI call
      2. Conversation history loaded
      3. Embedding + Qdrant search
      4. Context packed + citations built
      5. Gemini streaming response
      6. Assistant message saved with status=COMPLETED or FAILED

    After the stream completes, background memory extraction runs.
    """
    logger.info(
        "chat.stream_request",
        user_id=str(current_user.id),
        conversation_id=str(request.conversation_id) if request.conversation_id else "new",
    )

    async def event_stream():
        stream_completed = False
        response_message_id = None

        try:
            generator = stream_answer(
                db=db,
                user_id=current_user.id,
                question=request.question,
                conversation_id=request.conversation_id,
                top_k=request.top_k,
                score_threshold=request.score_threshold,
            )

            for event in generator:
                if event.get("type") == "done":
                    response_message_id = event.get("message_id")
                    stream_completed = True
                yield f"data: {json.dumps(event, default=str)}\n\n"

        except RAGError as e:
            logger.error("chat.stream_rag_error", error=str(e)[:200])
            error_event = {
                "type": "error",
                "detail": str(e),
                "conversation_id": str(request.conversation_id) if request.conversation_id else None,
            }
            yield f"data: {json.dumps(error_event)}\n\n"

        except Exception as e:
            logger.error(
                "chat.stream_unexpected_error",
                error=str(e)[:300],
            )
            error_event = {
                "type": "error",
                "detail": "An unexpected error occurred while streaming.",
            }
            yield f"data: {json.dumps(error_event)}\n\n"

        # Schedule background memory extraction only on successful completion
        if stream_completed and response_message_id and settings.ENABLE_AUTO_MEMORY:
            background_tasks.add_task(
                _run_background_memory_extraction,
                user_message=request.question,
                assistant_response="",  # answer will be read from DB
                user_id=current_user.id,
                source_message_id=response_message_id,
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
