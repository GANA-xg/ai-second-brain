"""
Memory Ranker — scores memories by relevance to the current question.

Uses keyword overlap, recency, and confidence to rank active memories
and return only the Top K for prompt injection.
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.memory import Memory
from app.services.memory_service import get_active_memories

logger = get_logger("memory_ranker")


def rank_memories_for_question(
    db: Session,
    user_id: uuid.UUID,
    question: str,
    *,
    max_memories: Optional[int] = None,
) -> list[Memory]:
    """Score and rank active memories by relevance to the current question.

    Ranking factors (weighted composite):
      1. Keyword overlap between question and memory content
      2. Confidence score (higher = better)
      3. Recency (more recent = slightly better)

    Returns the top N memories (default: MAX_PROMPT_MEMORIES).
    """
    if max_memories is None:
        max_memories = settings.MAX_PROMPT_MEMORIES

    if max_memories <= 0:
        return []

    # Get all active memories for this user
    all_memories = get_active_memories(
        db,
        user_id,
        limit=50,  # reasonable ceiling
    )

    if not all_memories:
        return []

    # Tokenise the question
    question_lower = question.lower()
    question_tokens = set(
        t for t in question_lower.split() if len(t) > 2
    )

    if not question_tokens:
        # No meaningful tokens → fall back to recency+confidence sort
        all_memories.sort(
            key=lambda m: (m.confidence, m.updated_at.timestamp()),
            reverse=True,
        )
        return all_memories[:max_memories]

    # Score each memory
    scored: list[tuple[float, Memory]] = []
    for mem in all_memories:
        score = _score_memory(mem, question_tokens)
        scored.append((score, mem))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    return [mem for _, mem in scored[:max_memories]]


def _score_memory(memory: Memory, question_tokens: set[str]) -> float:
    """Compute a composite relevance score for a memory given question tokens.

    Scoring formula (all 0.0–1.0):
      - keyword_score: fraction of question tokens present in memory content
      - confidence_score: raw confidence value
      - recency_boost: small boost for recent memories
    """
    mem_text = (memory.content or memory.value).lower()

    # Keyword overlap
    if question_tokens:
        match_count = sum(1 for t in question_tokens if t in mem_text)
        keyword_score = match_count / len(question_tokens)
    else:
        keyword_score = 0.0

    # Confidence score (0.0–1.0)
    confidence_score = memory.confidence

    # Recency boost: memories updated within last 7 days get a small lift
    recency_boost = 0.0
    now = __import__("datetime").datetime.now().timestamp()
    age_days = (now - memory.updated_at.timestamp()) / 86400
    if age_days < 7:
        recency_boost = 0.1 * (1.0 - age_days / 7)

    # Weighted composite
    score = (
        0.4 * keyword_score
        + 0.4 * confidence_score
        + 0.2 * recency_boost
    )

    return score
