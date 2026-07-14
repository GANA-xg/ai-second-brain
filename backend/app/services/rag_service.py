"""
Production RAG pipeline orchestrator.

Flow:
  User Question
      ↓
  Generate Query Embedding (reuses embedding_service)
      ↓
  Search Qdrant (reuses vector_service)
      ↓
  Retrieve Top-K Chunks
      ↓
  Pack Context (dedup, ranking, token budget)
      ↓
  Build Prompt (prompt_service template)
      ↓
  Call Gemini (gemini_service)
      ↓
  Generate Grounded Answer
      ↓
  Attach Citations
      ↓
  Store Retrieval Trace
      ↓
  Return Response

All business logic lives here — not in API routes.
"""

import time
import uuid
from typing import Any, Generator, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.cache_keys import search_key
from app.services.cache_service import cache_service, invalidate_search_cache
from app.models.chunk import Chunk
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message, MessageRole, MessageStatus
from app.models.retrieval_trace import RetrievalTrace
from app.schemas.chat import ChatResponse, Citation, RetrievedChunk
from app.services.embedding_service import generate_embeddings
from app.services.llm_service import LLMError, generate as gemini_generate
from app.services.llm_service import stream_generate as gemini_stream_generate
from app.services.prompt_service import get_prompt, build_memory_section
from app.services.vector_service import get_vector_service
from app.services.memory_ranker import rank_memories_for_question

logger = get_logger("rag_service")


class RAGError(Exception):
    """Raised when the RAG pipeline encounters an unrecoverable error."""


def _generate_query_embedding(question: str) -> list[float]:
    """Generate an embedding for the user's question.

    Reuses the existing embedding_service.generate_embeddings().
    Returns a flat list of floats.
    """
    embedding_bytes, failed, _ = generate_embeddings(
        [question],
        model_name=settings.EMBEDDING_MODEL,
        batch_size=1,
        max_retries=settings.EMBEDDING_MAX_RETRIES,
        timeout_seconds=settings.EMBEDDING_TIMEOUT_SECONDS,
    )
    if failed or not embedding_bytes or not embedding_bytes[0]:
        raise RAGError("Failed to generate query embedding")
    return np.frombuffer(embedding_bytes[0], dtype=np.float32).tolist()


def _pack_context(
    search_results: list[dict[str, Any]],
    db: Session,
    max_tokens: int = settings.MAX_CONTEXT_TOKENS,
) -> tuple[str, list[RetrievedChunk]]:
    """Build a packed context string from search results.

    Deduplicates chunks by chunk_id, preserves ranking, enforces token budget,
    and enriches with document metadata (filename, page).

    Returns:
        Tuple of (context_string, list_of_retrieved_chunk_objects).
    """
    seen_chunk_ids: set[str] = set()
    context_chunks: list[RetrievedChunk] = []
    estimated_tokens = 0
    overhead_per_chunk = 50  # rough token overhead for formatting per chunk

    chunk_ids_to_fetch = []
    for r in search_results:
        cid = r.get("chunk_id")
        if cid and cid not in seen_chunk_ids:
            seen_chunk_ids.add(cid)
            chunk_ids_to_fetch.append(uuid.UUID(cid))

    # Batch-fetch chunks from DB for content + document metadata
    chunks_map: dict[uuid.UUID, Chunk] = {}
    if chunk_ids_to_fetch:
        fetched = (
            db.query(Chunk)
            .filter(Chunk.id.in_(chunk_ids_to_fetch))
            .all()
        )
        for c in fetched:
            chunks_map[c.id] = c

    # Fetch document names for all involved document IDs
    doc_ids = set()
    for r in search_results:
        did = r.get("document_id")
        if did:
            doc_ids.add(uuid.UUID(did))

    docs_map: dict[uuid.UUID, Document] = {}
    if doc_ids:
        fetched_docs = (
            db.query(Document)
            .filter(Document.id.in_(list(doc_ids)))
            .all()
        )
        for d in fetched_docs:
            docs_map[d.id] = d

    for r in search_results:
        cid = r.get("chunk_id")
        if not cid or cid not in seen_chunk_ids:
            continue
        seen_chunk_ids.discard(cid)  # mark as processed

        chunk_id = uuid.UUID(cid)
        chunk = chunks_map.get(chunk_id)
        if not chunk:
            continue

        doc_id = uuid.UUID(r.get("document_id", "")) if r.get("document_id") else None
        doc = docs_map.get(doc_id) if doc_id else None

        content = chunk.content
        content_tokens = chunk.token_estimate or len(content) // 4

        # Check token budget before adding
        needed = estimated_tokens + content_tokens + overhead_per_chunk
        if needed > max_tokens:
            break

        estimated_tokens = needed

        retrieved = RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            score=r.get("score", 0.0),
            content=content,
            filename=doc.original_filename if doc else None,
            page=chunk.page_number,
            section=chunk.section,
            source_type=chunk.source_type,
        )
        context_chunks.append(retrieved)

    # Build context string
    context_parts = []
    for i, rc in enumerate(context_chunks, 1):
        source = rc.filename or "unknown"
        page_str = f" (page {rc.page})" if rc.page else ""
        section_str = f" Section: {rc.section}" if rc.section else ""
        context_parts.append(
            f"[{i}] Source: {source}{page_str}{section_str}\n"
            f"    Content: {rc.content}"
        )

    return "\n\n".join(context_parts), context_chunks


def _build_citations(context_chunks: list[RetrievedChunk]) -> list[Citation]:
    """Build citation list from retrieved chunk metadata.

    Each citation maps answer claims to source documents.
    """
    return [
        Citation(
            document_id=rc.document_id,
            filename=rc.filename or "unknown",
            chunk_id=rc.chunk_id,
            page=rc.page,
            score=rc.score,
        )
        for rc in context_chunks
    ]


def _get_or_create_conversation(
    db: Session,
    user_id: uuid.UUID,
    conversation_id: Optional[uuid.UUID],
    question: str,
) -> Conversation:
    """Get an existing conversation or create a new one.

    New conversations get a title derived from the first question.
    """
    if conversation_id:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if not conv:
            raise RAGError("Conversation not found or access denied")
        return conv

    title = (question[:95] + "...") if len(question) > 95 else question
    conv = Conversation(
        user_id=user_id,
        title=title,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _citations_to_dicts(citations: Optional[list[Citation]]) -> list[dict]:
    """Convert Citation objects to dicts with UUIDs serialized as strings.

    SQLAlchemy JSON columns cannot store raw UUID objects, so we convert
    them to strings before persisting.
    """
    return [
        {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in c.model_dump().items()}
        for c in citations
    ] if citations else []


def _store_messages(
    db: Session,
    conversation_id: uuid.UUID,
    question: str,
    answer: str,
    citations: Optional[list[Citation]] = None,
    message_status: MessageStatus = MessageStatus.COMPLETED,
) -> uuid.UUID:
    """Store user question and assistant answer as messages.

    Returns the assistant message ID for use in the response.
    """
    user_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=question,
    )
    db.add(user_msg)

    citation_dicts = _citations_to_dicts(citations)

    assistant_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=answer,
        status=message_status,
        citations=citation_dicts,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return assistant_msg.id


def _store_retrieval_trace(
    db: Session,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    question: str,
    embedding_model: str,
    prompt_version: str,
    gemini_model: str,
    top_k: int,
    score_threshold: float,
    retrieved_chunk_ids: list[str],
    document_ids: list[str],
    retrieval_scores: list[float],
    retrieval_latency_ms: float,
    gemini_prompt_tokens: int,
    gemini_completion_tokens: int,
    gemini_total_tokens: int,
    gemini_latency_ms: float,
    total_latency_ms: float,
) -> RetrievalTrace:
    """Persist a retrieval trace for debugging and observability."""
    trace = RetrievalTrace(
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        question=question[:1000],  # truncate to fit column
        embedding_model=embedding_model,
        prompt_version=prompt_version,
        gemini_model=gemini_model,
        top_k=top_k,
        score_threshold=score_threshold,
        retrieved_chunk_ids=retrieved_chunk_ids,
        document_ids=document_ids,
        retrieval_scores=retrieval_scores,
        retrieval_latency_ms=round(retrieval_latency_ms, 2),
        gemini_prompt_tokens=gemini_prompt_tokens,
        gemini_completion_tokens=gemini_completion_tokens,
        gemini_total_tokens=gemini_total_tokens,
        gemini_latency_ms=round(gemini_latency_ms, 2),
        total_latency_ms=round(total_latency_ms, 2),
    )
    db.add(trace)
    db.commit()
    return trace


def _no_context_response(
    db: Session,
    user_id: uuid.UUID,
    conversation_id: Optional[uuid.UUID],
    question: str,
    search_latency: float,
    pipeline_start: float,
    k: int,
    threshold: float,
) -> ChatResponse:
    """Build a fallback response when no relevant context is found."""
    conv = _get_or_create_conversation(db, user_id, conversation_id, question)
    no_context_answer = (
        "I could not find enough information in your uploaded documents "
        "to answer this question."
    )
    msg_id = _store_messages(db, conv.id, question, no_context_answer)
    total_latency = (time.time() - pipeline_start) * 1000

    _store_retrieval_trace(
        db,
        user_id=user_id,
        conversation_id=conv.id,
        message_id=msg_id,
        question=question,
        embedding_model=settings.EMBEDDING_MODEL,
        prompt_version=settings.PROMPT_VERSION,
        gemini_model=settings.GEMINI_MODEL,
        top_k=k,
        score_threshold=threshold,
        retrieved_chunk_ids=[],
        document_ids=[],
        retrieval_scores=[],
        retrieval_latency_ms=search_latency,
        gemini_prompt_tokens=0,
        gemini_completion_tokens=0,
        gemini_total_tokens=0,
        gemini_latency_ms=0.0,
        total_latency_ms=total_latency,
    )

    return ChatResponse(
        answer=no_context_answer,
        citations=[],
        conversation_id=conv.id,
        message_id=msg_id,
        retrieved_chunks=[],
        prompt_version=settings.PROMPT_VERSION,
        model_used=settings.GEMINI_MODEL,
    )


def _load_conversation_history(
    db: Session,
    conversation_id: Optional[uuid.UUID],
    user_id: uuid.UUID,
    max_messages: int = settings.MAX_HISTORY_MESSAGES,
) -> list[dict[str, str]]:
    """Load recent conversation history for multi-turn context.

    Returns a list of {role, content} dicts in chronological order,
    limited to the most recent `max_messages` messages.
    """
    if not conversation_id:
        return []

    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not conv:
        return []

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(max_messages)
        .all()
    )
    messages.reverse()  # back to chronological order

    return [
        {"role": msg.role.value.lower(), "content": msg.content}
        for msg in messages
    ]


def answer_question(
    *,
    db: Session,
    user_id: uuid.UUID,
    question: str,
    conversation_id: Optional[uuid.UUID] = None,
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None,
) -> ChatResponse:
    """Run the full RAG pipeline end-to-end.

    This is the single public entry point for the synchronous RAG system.
    """
    pipeline_start = time.time()

    # Resolve config overrides
    k = top_k if top_k is not None else settings.TOP_K
    threshold = score_threshold if score_threshold is not None else settings.SCORE_THRESHOLD

    logger.info(
        "rag.request_start",
        user_id=str(user_id),
        top_k=k,
        score_threshold=threshold,
        question_length=len(question),
    )

    # ── Step 1: Generate query embedding ──────────────────────────────
    embed_start = time.time()
    query_vector = _generate_query_embedding(question)
    embed_latency = (time.time() - embed_start) * 1000
    logger.info("rag.embedding_generated", latency_ms=round(embed_latency, 2))

    # ── Step 2: Search Qdrant (with cache) ────────────────────────────
    cache_key = search_key(user_id, question)
    search_results = cache_service.get(cache_key)
    search_latency = 0.0  # default for cache hits
    if search_results is not None:
        logger.info(
            "rag.search_cache_hit",
            user_id=str(user_id),
            results=len(search_results),
        )
    else:
        vector_service = get_vector_service()
        search_start = time.time()
        search_results = vector_service.search(
            user_id=user_id,
            query_vector=query_vector,
            limit=k,
            score_threshold=threshold,
        )
        search_latency = (time.time() - search_start) * 1000

        logger.info(
            "rag.search_complete",
            results=len(search_results),
            latency_ms=round(search_latency, 2),
        )

        # Cache vector search results (NOT Gemini answers)
        cache_service.set(
            cache_key,
            search_results,
            ttl=settings.CACHE_SEARCH_TTL,
        )

    if not search_results:
        logger.info("rag.no_results", user_id=str(user_id))
        return _no_context_response(db, user_id, conversation_id, question, search_latency, pipeline_start, k, threshold)

    # ── Step 3: Pack context ──────────────────────────────────────────
    context_str, context_chunks = _pack_context(search_results, db)

    logger.info(
        "rag.context_packed",
        chunks_in_context=len(context_chunks),
        context_length=len(context_str),
    )

    if not context_chunks:
        return _no_context_response(db, user_id, conversation_id, question, search_latency, pipeline_start, k, threshold)

    # ── Step 4: Inject user memories ───────────────────────────────────
    ranked_memories = rank_memories_for_question(db, user_id, question)
    memory_section = build_memory_section(
        [{"content": m.content} for m in ranked_memories]
    )

    # ── Step 5: Build prompt (with proper ordering) ────────────────────
    # Order: System Instruction → User Memory → Retrieved Documents → Question
    prompt_template = get_prompt(settings.PROMPT_VERSION)
    full_prompt = prompt_template.format_prompt(context_str, question)

    # Prepend memory section OUTSIDE the Context: block
    if memory_section:
        full_prompt = memory_section + "\n\n" + full_prompt

    # ── Step 6: Call Gemini ───────────────────────────────────────────
    gemini_start = time.time()
    gemini_result = gemini_generate(
        prompt=full_prompt,
        system_instruction=prompt_template.system_instruction,
        model_name=settings.GEMINI_MODEL,
        max_output_tokens=settings.MAX_RESPONSE_TOKENS,
    )
    gemini_latency = (time.time() - gemini_start) * 1000

    # ── Step 7: Build citations ───────────────────────────────────────
    citations = _build_citations(context_chunks)

    # ── Step 8: Store conversation / messages ─────────────────────────
    conv = _get_or_create_conversation(db, user_id, conversation_id, question)
    msg_id = _store_messages(db, conv.id, question, gemini_result["text"], citations)

    # ── Step 9: Store retrieval trace ─────────────────────────────────
    total_latency = (time.time() - pipeline_start) * 1000

    retrieved_chunk_ids = [str(rc.chunk_id) for rc in context_chunks]
    doc_ids = list({str(rc.document_id) for rc in context_chunks})
    retrieval_scores = [rc.score for rc in context_chunks]

    _store_retrieval_trace(
        db,
        user_id=user_id,
        conversation_id=conv.id,
        message_id=msg_id,
        question=question,
        embedding_model=settings.EMBEDDING_MODEL,
        prompt_version=settings.PROMPT_VERSION,
        gemini_model=settings.GEMINI_MODEL,
        top_k=k,
        score_threshold=threshold,
        retrieved_chunk_ids=retrieved_chunk_ids,
        document_ids=doc_ids,
        retrieval_scores=retrieval_scores,
        retrieval_latency_ms=search_latency,
        gemini_prompt_tokens=gemini_result["prompt_tokens"],
        gemini_completion_tokens=gemini_result["completion_tokens"],
        gemini_total_tokens=gemini_result["total_tokens"],
        gemini_latency_ms=gemini_result["latency_ms"],
        total_latency_ms=total_latency,
    )

    logger.info(
        "rag.request_complete",
        user_id=str(user_id),
        conversation_id=str(conv.id),
        chunks_retrieved=len(context_chunks),
        citations=len(citations),
        total_latency_ms=round(total_latency, 2),
    )

    return ChatResponse(
        answer=gemini_result["text"],
        citations=citations,
        conversation_id=conv.id,
        message_id=msg_id,
        retrieved_chunks=context_chunks,
        prompt_version=settings.PROMPT_VERSION,
        model_used=settings.GEMINI_MODEL,
    )


class _iter_capture_return:
    """Iterate a generator, preserving its return value.

    A ``for`` loop over a generator discards ``StopIteration.value``
    (the generator's return value).  This wrapper keeps it as
    ``.return_value`` so the caller can read it after iteration.

    Usage::

        wrapped = _iter_capture_return(some_generator())
        for item in wrapped:
            ...
        result = wrapped.return_value  # generator's return value
    """

    __slots__ = ('_gen', 'return_value')

    def __init__(self, gen):
        self._gen = gen
        self.return_value = None

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._gen)
        except StopIteration as e:
            self.return_value = e.value
            raise


def stream_answer(
    *,
    db: Session,
    user_id: uuid.UUID,
    question: str,
    conversation_id: Optional[uuid.UUID] = None,
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None,
) -> Generator[dict[str, Any], None, ChatResponse]:
    """Stream a RAG answer token-by-token via Gemini streaming.

    Yields SSE-compatible event dicts:
      - {"type": "token", "content": "Hello"}
      - {"type": "citation", "citations": [...]}
      - {"type": "done", "citations": [...], "conversation_id": ..., "message_id": ...}
      - {"type": "error", "detail": "..."} (on failure before partial output)

    Returns the final ChatResponse synchronously after streaming completes.
    """
    pipeline_start = time.time()

    # Resolve config overrides
    k = top_k if top_k is not None else settings.TOP_K
    threshold = score_threshold if score_threshold is not None else settings.SCORE_THRESHOLD

    logger.info(
        "rag.stream_start",
        user_id=str(user_id),
        conversation_id=str(conversation_id) if conversation_id else "new",
        top_k=k,
        score_threshold=threshold,
    )

    # ── Step 1: Get or create conversation ────────────────────────────
    conv = _get_or_create_conversation(db, user_id, conversation_id, question)

    # ── Step 2: Load conversation history ─────────────────────────────
    history = _load_conversation_history(db, conv.id, user_id)

    if history:
        logger.info(
            "rag.history_loaded",
            conversation_id=str(conv.id),
            history_count=len(history),
        )

    # ── Step 3: Generate query embedding ──────────────────────────────
    embed_start = time.time()
    try:
        query_vector = _generate_query_embedding(question)
    except RAGError as e:
        logger.error("rag.embedding_failed", error=str(e)[:200])
        yield {"type": "error", "detail": str(e)}
        return _no_context_response(db, user_id, conv.id, question, 0, pipeline_start, k, threshold)

    # ── Step 4: Search Qdrant (with cache) ────────────────────────────
    cache_key = search_key(user_id, question)
    search_results = cache_service.get(cache_key)
    search_latency = 0.0  # default for cache hits
    if search_results is not None:
        logger.info(
            "rag.search_cache_hit",
            user_id=str(user_id),
            conversation_id=str(conv.id),
            results=len(search_results),
        )
    else:
        vector_service = get_vector_service()
        search_start = time.time()
        search_results = vector_service.search(
            user_id=user_id,
            query_vector=query_vector,
            limit=k,
            score_threshold=threshold,
        )
        search_latency = (time.time() - search_start) * 1000
        logger.info(
            "rag.stream_search_complete",
            results=len(search_results),
            latency_ms=round(search_latency, 2),
        )
        # Cache vector search results
        cache_service.set(
            cache_key,
            search_results,
            ttl=settings.CACHE_SEARCH_TTL,
        )

    # ── Step 5: Pack context ──────────────────────────────────────────
    if not search_results:
        logger.info("rag.stream_no_results", user_id=str(user_id), conversation_id=str(conv.id))
        answer = "I could not find enough information in your uploaded documents to answer this question."
        msg_id = _store_messages(db, conv.id, question, answer, message_status=MessageStatus.COMPLETED)
        total_latency = (time.time() - pipeline_start) * 1000
        _store_retrieval_trace(
            db, user_id=user_id, conversation_id=conv.id, message_id=msg_id,
            question=question, embedding_model=settings.EMBEDDING_MODEL,
            prompt_version=settings.PROMPT_VERSION, gemini_model=settings.GEMINI_MODEL,
            top_k=k, score_threshold=threshold,
            retrieved_chunk_ids=[], document_ids=[], retrieval_scores=[],
            retrieval_latency_ms=search_latency,
            gemini_prompt_tokens=0, gemini_completion_tokens=0, gemini_total_tokens=0,
            gemini_latency_ms=0.0, total_latency_ms=total_latency,
        )
        yield {"type": "token", "content": answer}
        yield {"type": "done", "citations": [], "conversation_id": conv.id, "message_id": msg_id}
        return ChatResponse(
            answer=answer, citations=[], conversation_id=conv.id, message_id=msg_id,
            retrieved_chunks=[], prompt_version=settings.PROMPT_VERSION, model_used=settings.GEMINI_MODEL,
        )

    context_str, context_chunks = _pack_context(search_results, db)

    if not context_chunks:
        answer = "I could not find enough information in your uploaded documents to answer this question."
        msg_id = _store_messages(db, conv.id, question, answer, message_status=MessageStatus.COMPLETED)
        total_latency = (time.time() - pipeline_start) * 1000
        _store_retrieval_trace(
            db, user_id=user_id, conversation_id=conv.id, message_id=msg_id,
            question=question, embedding_model=settings.EMBEDDING_MODEL,
            prompt_version=settings.PROMPT_VERSION, gemini_model=settings.GEMINI_MODEL,
            top_k=k, score_threshold=threshold,
            retrieved_chunk_ids=[], document_ids=[], retrieval_scores=[],
            retrieval_latency_ms=search_latency,
            gemini_prompt_tokens=0, gemini_completion_tokens=0, gemini_total_tokens=0,
            gemini_latency_ms=0.0, total_latency_ms=total_latency,
        )
        yield {"type": "token", "content": answer}
        yield {"type": "done", "citations": [], "conversation_id": conv.id, "message_id": msg_id}
        return ChatResponse(
            answer=answer, citations=[], conversation_id=conv.id, message_id=msg_id,
            retrieved_chunks=[], prompt_version=settings.PROMPT_VERSION, model_used=settings.GEMINI_MODEL,
        )

    # ── Step 6: Build citations ───────────────────────────────────────
    citations = _build_citations(context_chunks)
    # Yield citations so the client can show them early
    yield {"type": "citation", "citations": [c.model_dump() for c in citations]}

    # ── Step 7: Inject user memories ──────────────────────────────────
    ranked_memories = rank_memories_for_question(db, user_id, question)
    memory_section = build_memory_section(
        [{"content": m.content} for m in ranked_memories]
    )

    # ── Step 8: Build prompt (with proper ordering) ────────────────────
    # Order: System Instruction → User Memory → Conversation History → Retrieved Documents → Question
    prompt_template = get_prompt(settings.PROMPT_VERSION)

    # Build context parts in the right order: History → Documents
    context_parts = []
    if history:
        history_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in history
        )
        context_parts.append(f"Conversation history:\n{history_text}")
    context_parts.append(context_str)

    combined_context = "\n\n".join(p for p in context_parts if p)
    full_prompt = prompt_template.format_prompt(combined_context, question)

    # Prepend memory section OUTSIDE the Context: block
    if memory_section:
        full_prompt = memory_section + "\n\n" + full_prompt

    # ── Save user message BEFORE streaming ────────────────────────────
    user_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content=question,
    )
    db.add(user_msg)
    db.flush()

    # Create a placeholder assistant message (PENDING status)
    assistant_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content="",
        status=MessageStatus.PENDING,
        citations=[],
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    assistant_msg_id = assistant_msg.id

    # ── Step 9: Stream from Gemini ────────────────────────────────────
    full_answer = ""
    gemini_start = time.time()
    gemini_latency = 0.0
    gemini_prompt_tokens = 0
    gemini_completion_tokens = 0
    gemini_total_tokens = 0
    stream_failed = False

    try:
        gemini_gen = gemini_stream_generate(
            prompt=full_prompt,
            system_instruction=prompt_template.system_instruction,
            conversation_history=history if history else None,
            model_name=settings.GEMINI_MODEL,
            max_output_tokens=settings.MAX_RESPONSE_TOKENS,
            timeout_seconds=settings.CHAT_TIMEOUT_SECONDS,
        )
        gemini_stream = _iter_capture_return(gemini_gen)
        for event in gemini_stream:
            if event["type"] == "token":
                full_answer += event["content"]
                yield {"type": "token", "content": event["content"]}

        gemini_latency = (time.time() - gemini_start) * 1000

        # Capture token counts from the inner generator's return value
        gemini_result = gemini_stream.return_value or {}
        gemini_prompt_tokens = gemini_result.get("prompt_tokens", gemini_prompt_tokens)
        gemini_completion_tokens = gemini_result.get("completion_tokens", gemini_completion_tokens)
        gemini_total_tokens = gemini_result.get("total_tokens", gemini_total_tokens)

    except LLMError as e:
        gemini_latency = (time.time() - gemini_start) * 1000
        stream_failed = True
        error_msg = str(e)

        # Update assistant message to FAILED
        assistant_msg.content = error_msg[:5000]
        assistant_msg.status = MessageStatus.FAILED
        assistant_msg.error_metadata = {"error": error_msg, "latency_ms": round(gemini_latency, 2)}
        db.commit()

        total_latency = (time.time() - pipeline_start) * 1000

        _store_retrieval_trace(
            db, user_id=user_id, conversation_id=conv.id, message_id=assistant_msg_id,
            question=question, embedding_model=settings.EMBEDDING_MODEL,
            prompt_version=settings.PROMPT_VERSION, gemini_model=settings.GEMINI_MODEL,
            top_k=k, score_threshold=threshold,
            retrieved_chunk_ids=[str(rc.chunk_id) for rc in context_chunks],
            document_ids=list({str(rc.document_id) for rc in context_chunks}),
            retrieval_scores=[rc.score for rc in context_chunks],
            retrieval_latency_ms=search_latency,
            gemini_prompt_tokens=0, gemini_completion_tokens=0, gemini_total_tokens=0,
            gemini_latency_ms=gemini_latency, total_latency_ms=total_latency,
        )

        yield {"type": "error", "detail": "The AI service encountered an error. Please try again."}
        logger.error("rag.stream_gemini_failed", error=error_msg[:200], conversation_id=str(conv.id))
        return ChatResponse(
            answer=error_msg, citations=citations, conversation_id=conv.id,
            message_id=assistant_msg_id, retrieved_chunks=context_chunks,
            prompt_version=settings.PROMPT_VERSION, model_used=settings.GEMINI_MODEL,
        )

    # ── Step 10: Update assistant message to COMPLETED ─────────────────
    if not stream_failed:
        assistant_msg.content = full_answer
        assistant_msg.status = MessageStatus.COMPLETED
        assistant_msg.citations = _citations_to_dicts(citations)
        db.commit()

    # ── Step 11: Store retrieval trace ────────────────────────────────
    total_latency = (time.time() - pipeline_start) * 1000

    retrieved_chunk_ids = [str(rc.chunk_id) for rc in context_chunks]
    doc_ids = list({str(rc.document_id) for rc in context_chunks})
    retrieval_scores_list = [rc.score for rc in context_chunks]

    _store_retrieval_trace(
        db,
        user_id=user_id,
        conversation_id=conv.id,
        message_id=assistant_msg_id,
        question=question,
        embedding_model=settings.EMBEDDING_MODEL,
        prompt_version=settings.PROMPT_VERSION,
        gemini_model=settings.GEMINI_MODEL,
        top_k=k,
        score_threshold=threshold,
        retrieved_chunk_ids=retrieved_chunk_ids,
        document_ids=doc_ids,
        retrieval_scores=retrieval_scores_list,
        retrieval_latency_ms=search_latency,
        gemini_prompt_tokens=gemini_prompt_tokens,
        gemini_completion_tokens=gemini_completion_tokens,
        gemini_total_tokens=gemini_total_tokens,
        gemini_latency_ms=gemini_latency,
        total_latency_ms=total_latency,
    )

    # ── Final yield: done ─────────────────────────────────────────────
    yield {
        "type": "done",
        "citations": [c.model_dump() for c in citations],
        "conversation_id": conv.id,
        "message_id": assistant_msg_id,
    }

    logger.info(
        "rag.stream_complete",
        user_id=str(user_id),
        conversation_id=str(conv.id),
        chunks_retrieved=len(context_chunks),
        citations=len(citations),
        total_latency_ms=round(total_latency, 2),
    )

    return ChatResponse(
        answer=full_answer,
        citations=citations,
        conversation_id=conv.id,
        message_id=assistant_msg_id,
        retrieved_chunks=context_chunks,
        prompt_version=settings.PROMPT_VERSION,
        model_used=settings.GEMINI_MODEL,
    )
