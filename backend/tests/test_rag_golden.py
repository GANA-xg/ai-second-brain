"""Golden-set regression tests for the RAG pipeline.

These tests pin a handful of representative questions to stable,
deterministic outputs so we can catch answer-quality regressions
without depending on live model or vector infrastructure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from app.models.chunk import Chunk
from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.schemas.chat import RetrievedChunk


@dataclass(frozen=True)
class GoldenCase:
    name: str
    question: str
    search_results: list[dict[str, str | float]]
    expected_answer_fragment: str
    expected_filenames: list[str]


@pytest.fixture
def golden_documents(db_session, user):
    """Create a small corpus used by the golden set."""
    tax_doc = Document(
        user_id=user.id,
        filename="tax_policy.txt",
        original_filename="tax_policy.txt",
        extension="txt",
        mime_type="text/plain",
        file_size=128,
        status=DocumentStatus.READY,
        storage_key="uploads/tax_policy.txt",
    )
    travel_doc = Document(
        user_id=user.id,
        filename="travel_policy.txt",
        original_filename="travel_policy.txt",
        extension="txt",
        mime_type="text/plain",
        file_size=128,
        status=DocumentStatus.READY,
        storage_key="uploads/travel_policy.txt",
    )
    db_session.add_all([tax_doc, travel_doc])
    db_session.flush()

    tax_chunk = Chunk(
        document_id=tax_doc.id,
        chunk_index=0,
        content="Employees may claim reimbursement for approved work travel.",
        source_type="txt",
        page_number=None,
        section="Reimbursements",
        character_start=0,
        character_end=68,
        token_estimate=18,
    )
    travel_chunk = Chunk(
        document_id=travel_doc.id,
        chunk_index=0,
        content="Personal travel is not reimbursable unless pre-approved.",
        source_type="txt",
        page_number=None,
        section="Travel Rules",
        character_start=0,
        character_end=61,
        token_estimate=16,
    )
    db_session.add_all([tax_chunk, travel_chunk])
    db_session.commit()

    return {
        "tax_doc": tax_doc,
        "travel_doc": travel_doc,
        "tax_chunk": tax_chunk,
        "travel_chunk": travel_chunk,
    }


@pytest.fixture
def golden_cases(golden_documents):
    tax_doc = golden_documents["tax_doc"]
    travel_doc = golden_documents["travel_doc"]
    tax_chunk = golden_documents["tax_chunk"]
    travel_chunk = golden_documents["travel_chunk"]

    return [
        GoldenCase(
            name="work-travel",
            question="Can I claim reimbursement for work travel?",
            search_results=[
                {
                    "chunk_id": str(tax_chunk.id),
                    "document_id": str(tax_doc.id),
                    "score": 0.98,
                }
            ],
            expected_answer_fragment="work travel",
            expected_filenames=["tax_policy.txt"],
        ),
        GoldenCase(
            name="personal-travel",
            question="Is personal travel reimbursable?",
            search_results=[
                {
                    "chunk_id": str(travel_chunk.id),
                    "document_id": str(travel_doc.id),
                    "score": 0.97,
                }
            ],
            expected_answer_fragment="not reimbursable",
            expected_filenames=["travel_policy.txt"],
        ),
    ]


def _fake_embedding(_: str) -> list[float]:
    return [0.1, 0.2, 0.3]


def _fake_gemini_answer(expected_fragment: str):
    def _inner(*args, **kwargs):
        prompt = kwargs.get("prompt", "")
        return {
            "text": f"Based on the policy, {expected_fragment}.",
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
            "latency_ms": 5.0,
            "prompt": prompt,
        }

    return _inner


@pytest.mark.parametrize("case_index", [0, 1])
def test_rag_golden_set(db_session, user, golden_cases, case_index):
    """Regression test for representative RAG questions."""
    case = golden_cases[case_index]
    conversation = Conversation(user_id=user.id, title=case.question)
    db_session.add(conversation)
    db_session.commit()

    with patch("app.services.rag_service._generate_query_embedding", side_effect=_fake_embedding):
        with patch("app.services.rag_service.get_vector_service") as mock_vector_service:
            mock_vector = MagicMock()
            mock_vector.search.return_value = case.search_results
            mock_vector_service.return_value = mock_vector

            with patch("app.services.rag_service.gemini_generate", side_effect=_fake_gemini_answer(case.expected_answer_fragment)):
                from app.services.rag_service import answer_question

                response = answer_question(
                    db=db_session,
                    user_id=user.id,
                    question=case.question,
                    conversation_id=conversation.id,
                )

    assert case.expected_answer_fragment in response.answer
    assert response.citations
    assert [citation.filename for citation in response.citations] == case.expected_filenames
    assert response.conversation_id == conversation.id
    assert response.message_id is not None


def test_rag_golden_context_includes_source_labels(db_session, user, golden_documents):
    """The packed context should stay readable for regression debugging."""
    from app.services.rag_service import _pack_context

    tax_doc = golden_documents["tax_doc"]
    tax_chunk = golden_documents["tax_chunk"]

    context, chunks = _pack_context(
        [
            {
                "chunk_id": str(tax_chunk.id),
                "document_id": str(tax_doc.id),
                "score": 0.99,
            }
        ],
        db_session,
    )

    assert "Source: tax_policy.txt" in context
    assert "Employees may claim reimbursement" in context
    assert len(chunks) == 1
    assert isinstance(chunks[0], RetrievedChunk)
