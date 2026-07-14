"""
Tests for the Chat System (Part 9).

Covers:
  - Conversation CRUD (create, list, get, update, delete)
  - Message persistence (user before AI, assistant after)
  - Pagination
  - Ownership checks
  - Streaming endpoint
  - Conversation history loading
  - Failed Gemini calls → assistant FAILED saved
  - Conversation deletion cascade
  - Auto-title generation
  - Stream events (token, citation, done, error)
  - Config validation for chat settings
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import ANY, MagicMock, PropertyMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole, MessageStatus
from app.models.retrieval_trace import RetrievalTrace


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conversation(db_session, user):
    """Create and return a conversation owned by the test user."""
    conv = Conversation(
        user_id=user.id,
        title="Test Conversation",
    )
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    return conv


@pytest.fixture
def user_conversation(db_session, registered_user):
    """Create a conversation owned by the registered (authenticated) user."""
    from app.models.conversation import Conversation as ConvModel

    user_id = uuid.UUID(registered_user[2]["id"])
    conv = ConvModel(
        user_id=user_id,
        title="Test Conversation",
    )
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    return conv


@pytest.fixture
def user_conversation_with_messages(db_session, registered_user):
    """Create a conversation with several messages owned by registered user."""
    from app.models.conversation import Conversation as ConvModel

    user_id = uuid.UUID(registered_user[2]["id"])
    conv = ConvModel(user_id=user_id, title="Multi-Message Conv")
    db_session.add(conv)
    db_session.flush()

    messages = []
    for i in range(5):
        user_msg = Message(
            conversation_id=conv.id,
            role=MessageRole.USER,
            content=f"User message {i+1}",
        )
        db_session.add(user_msg)
        messages.append(user_msg)

        assistant_msg = Message(
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content=f"Assistant response {i+1}",
            status=MessageStatus.COMPLETED,
        )
        db_session.add(assistant_msg)
        messages.append(assistant_msg)

    db_session.commit()
    db_session.refresh(conv)
    return conv, messages


@pytest.fixture
def user_conversation_with_30_messages(db_session, registered_user):
    """Create a conversation with 30 messages owned by registered user."""
    from app.models.conversation import Conversation as ConvModel

    user_id = uuid.UUID(registered_user[2]["id"])
    conv = ConvModel(user_id=user_id, title="Pagination Test")
    db_session.add(conv)
    db_session.flush()

    for i in range(15):
        db_session.add(Message(
            conversation_id=conv.id,
            role=MessageRole.USER,
            content=f"User message {i+1}",
        ))
        db_session.add(Message(
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content=f"Assistant response {i+1}",
            status=MessageStatus.COMPLETED,
        ))

    db_session.commit()
    return conv


@pytest.fixture
def other_user(db_session):
    """Create and return a second test user."""
    from app.models.user import User
    from app.core.security import hash_password

    user = User(
        email="other@example.com",
        full_name="Other User",
        hashed_password=hash_password("OtherPass123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_conversation(db_session, other_user):
    """Create a conversation owned by another user."""
    conv = Conversation(
        user_id=other_user.id,
        title="Other's Conversation",
    )
    db_session.add(conv)
    db_session.commit()
    db_session.refresh(conv)
    return conv


@pytest.fixture
def conversation_with_messages(db_session, user):
    """Create a conversation with several messages."""
    conv = Conversation(user_id=user.id, title="Multi-Message Conv")
    db_session.add(conv)
    db_session.flush()

    messages = []
    for i in range(5):
        user_msg = Message(
            conversation_id=conv.id,
            role=MessageRole.USER,
            content=f"User message {i+1}",
        )
        db_session.add(user_msg)
        messages.append(user_msg)

        assistant_msg = Message(
            conversation_id=conv.id,
            role=MessageRole.ASSISTANT,
            content=f"Assistant response {i+1}",
            status=MessageStatus.COMPLETED,
        )
        db_session.add(assistant_msg)
        messages.append(assistant_msg)

    db_session.commit()
    db_session.refresh(conv)
    return conv, messages


# ---------------------------------------------------------------------------
# Conversation CRUD Tests
# ---------------------------------------------------------------------------


class TestConversationCRUD:
    """Conversation creation, listing, retrieval, update, and deletion."""

    # --- CREATE ---

    def test_create_conversation(self, client: TestClient, auth_headers):
        """Creating a conversation should return 201 with conversation data."""
        response = client.post(
            "/api/v1/chat/conversations",
            json={"title": "My New Chat"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["title"] == "My New Chat"
        assert "id" in data
        assert "created_at" in data

    def test_create_conversation_without_title(self, client: TestClient, auth_headers):
        """Creating a conversation without a title should use default."""
        response = client.post(
            "/api/v1/chat/conversations",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["title"] == "New conversation"

    def test_create_conversation_requires_auth(self, client: TestClient):
        """Unauthenticated conversation creation should be rejected."""
        response = client.post(
            "/api/v1/chat/conversations",
            json={"title": "Hacked"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # --- LIST ---

    def test_list_conversations(self, client: TestClient, auth_headers, user_conversation):
        """Listing conversations should return the user's conversations."""
        response = client.get(
            "/api/v1/chat/conversations",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "conversations" in data
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["id"] == str(user_conversation.id)

    def test_list_conversations_excludes_other_users(
        self,
        client: TestClient,
        auth_headers,
        user_conversation,
        other_conversation,
    ):
        """List should only show the current user's conversations."""
        response = client.get(
            "/api/v1/chat/conversations",
            headers=auth_headers,
        )
        data = response.json()
        ids = [c["id"] for c in data["conversations"]]
        assert str(user_conversation.id) in ids
        assert str(other_conversation.id) not in ids

    def test_list_conversations_empty(self, client: TestClient, auth_headers):
        """A user with no conversations should get an empty list."""
        response = client.get(
            "/api/v1/chat/conversations",
            headers=auth_headers,
        )
        data = response.json()
        assert data["conversations"] == []
        assert data["total"] == 0

    def test_list_conversations_requires_auth(self, client: TestClient):
        """Unauthenticated list should be rejected."""
        response = client.get("/api/v1/chat/conversations")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_conversations_message_count(
        self,
        client: TestClient,
        auth_headers,
        user_conversation_with_messages,
    ):
        """List response should include correct message_count per conversation."""
        conv, msgs = user_conversation_with_messages
        response = client.get("/api/v1/chat/conversations", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        match = [c for c in data["conversations"] if c["id"] == str(conv.id)]
        assert len(match) == 1, "conversation not found in list"
        assert match[0]["message_count"] == len(msgs), (
            f"expected {len(msgs)}, got {match[0]['message_count']}"
        )

    # --- GET ---

    def test_get_conversation(
        self,
        client: TestClient,
        auth_headers,
        user_conversation,
    ):
        """Getting a conversation should return full details."""
        response = client.get(
            f"/api/v1/chat/conversations/{user_conversation.id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(user_conversation.id)
        assert data["title"] == "Test Conversation"
        assert data["messages"] == []
        assert data["message_count"] == 0

    def test_get_conversation_not_found(
        self,
        client: TestClient,
        auth_headers,
    ):
        """Non-existent conversation should return 404."""
        response = client.get(
            f"/api/v1/chat/conversations/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_conversation_denied(
        self,
        client: TestClient,
        auth_headers,
        other_conversation,
    ):
        """Getting another user's conversation should return 403."""
        response = client.get(
            f"/api/v1/chat/conversations/{other_conversation.id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_conversation_requires_auth(
        self,
        client: TestClient,
        conversation,
    ):
        """Unauthenticated get should be rejected."""
        response = client.get(
            f"/api/v1/chat/conversations/{conversation.id}",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # --- UPDATE (RENAME) ---

    def test_update_conversation_title(
        self,
        client: TestClient,
        auth_headers,
        user_conversation,
    ):
        """Updating a conversation title should work."""
        response = client.patch(
            f"/api/v1/chat/conversations/{user_conversation.id}",
            json={"title": "Renamed Conversation"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] == "Renamed Conversation"

    def test_update_conversation_denied(
        self,
        client: TestClient,
        auth_headers,
        other_conversation,
    ):
        """Updating another user's conversation should return 403."""
        response = client.patch(
            f"/api/v1/chat/conversations/{other_conversation.id}",
            json={"title": "Hacked Title"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_conversation_not_found(
        self,
        client: TestClient,
        auth_headers,
    ):
        """Updating a non-existent conversation should return 404."""
        response = client.patch(
            f"/api/v1/chat/conversations/{uuid.uuid4()}",
            json={"title": "Ghost"},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # --- DELETE ---

    def test_delete_conversation(
        self,
        client: TestClient,
        auth_headers,
        user_conversation,
    ):
        """Deleting a conversation should return 204 and remove it."""
        response = client.delete(
            f"/api/v1/chat/conversations/{user_conversation.id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify it's gone
        get_response = client.get(
            f"/api/v1/chat/conversations/{user_conversation.id}",
            headers=auth_headers,
        )
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_conversation_cascade(
        self,
        client: TestClient,
        auth_headers,
        db_session,
        registered_user,
    ):
        """Deleting a conversation should cascade-delete its messages."""
        from app.models.conversation import Conversation as ConvModel
        user_id = uuid.UUID(registered_user[2]["id"])
        conv = ConvModel(user_id=user_id, title="To Delete")
        db_session.add(conv)
        db_session.commit()

        msg = Message(
            conversation_id=conv.id,
            role=MessageRole.USER,
            content="Will be deleted",
        )
        db_session.add(msg)
        db_session.commit()

        response = client.delete(
            f"/api/v1/chat/conversations/{conv.id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Messages should also be deleted
        remaining = (
            db_session.query(Message)
            .filter(Message.conversation_id == conv.id)
            .count()
        )
        assert remaining == 0

    def test_delete_conversation_denied(
        self,
        client: TestClient,
        auth_headers,
        other_conversation,
    ):
        """Deleting another user's conversation should return 403."""
        response = client.delete(
            f"/api/v1/chat/conversations/{other_conversation.id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_conversation_not_found(
        self,
        client: TestClient,
        auth_headers,
    ):
        """Deleting a non-existent conversation should return 404."""
        response = client.delete(
            f"/api/v1/chat/conversations/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_conversation_requires_auth(
        self,
        client: TestClient,
        conversation,
    ):
        """Unauthenticated delete should be rejected."""
        response = client.delete(
            f"/api/v1/chat/conversations/{conversation.id}",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Message Persistence Tests
# ---------------------------------------------------------------------------


class TestMessagePersistence:
    """Messages are saved correctly, including failed states."""

    def test_get_messages_empty(
        self,
        client: TestClient,
        auth_headers,
        user_conversation,
    ):
        """A conversation with no messages should return empty list."""
        response = client.get(
            f"/api/v1/chat/conversations/{user_conversation.id}/messages",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["messages"] == []
        assert data["total"] == 0

    def test_get_messages_requires_auth(
        self,
        client: TestClient,
        conversation,
    ):
        """Unauthenticated message retrieval should be rejected."""
        response = client.get(
            f"/api/v1/chat/conversations/{conversation.id}/messages",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_messages_denied(
        self,
        client: TestClient,
        auth_headers,
        other_conversation,
    ):
        """Getting messages from another user's conversation should return 403."""
        response = client.get(
            f"/api/v1/chat/conversations/{other_conversation.id}/messages",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_messages_ordered_by_created_at(
        self,
        client: TestClient,
        auth_headers,
        user_conversation_with_messages,
    ):
        """Messages should be returned in chronological order."""
        conv, _ = user_conversation_with_messages
        response = client.get(
            f"/api/v1/chat/conversations/{conv.id}/messages",
            headers=auth_headers,
        )
        data = response.json()
        contents = [m["content"] for m in data["messages"]]
        # Messages are USER, ASSISTANT, USER, ASSISTANT, ...
        assert contents[0] == "User message 1"
        assert contents[1] == "Assistant response 1"
        assert contents[-1] == "Assistant response 5"


# ---------------------------------------------------------------------------
# Pagination Tests
# ---------------------------------------------------------------------------


class TestPagination:
    """Message pagination works correctly."""

    def test_default_page_size(
        self,
        client: TestClient,
        auth_headers,
        user_conversation_with_30_messages,
    ):
        """Default page size should be 20."""
        conv = user_conversation_with_30_messages
        response = client.get(
            f"/api/v1/chat/conversations/{conv.id}/messages",
            headers=auth_headers,
        )
        data = response.json()
        assert len(data["messages"]) == 20
        assert data["total"] == 30
        assert data["has_next"] is True

    def test_second_page(
        self,
        client: TestClient,
        auth_headers,
        user_conversation_with_30_messages,
    ):
        """Second page should return the remaining messages."""
        conv = user_conversation_with_30_messages
        response = client.get(
            f"/api/v1/chat/conversations/{conv.id}/messages",
            params={"page": 2, "page_size": 20},
            headers=auth_headers,
        )
        data = response.json()
        assert len(data["messages"]) == 10
        assert data["has_next"] is False

    def test_custom_page_size(
        self,
        client: TestClient,
        auth_headers,
        user_conversation_with_30_messages,
    ):
        """Custom page_size should be honored."""
        conv = user_conversation_with_30_messages
        response = client.get(
            f"/api/v1/chat/conversations/{conv.id}/messages",
            params={"page": 1, "page_size": 5},
            headers=auth_headers,
        )
        data = response.json()
        assert len(data["messages"]) == 5
        assert data["total"] == 30
        assert data["has_next"] is True

    def test_page_size_not_exceed_max(
        self,
        client: TestClient,
        auth_headers,
        user_conversation_with_30_messages,
    ):
        """Page size should be capped at MAX_PAGE_SIZE."""
        conv = user_conversation_with_30_messages
        response = client.get(
            f"/api/v1/chat/conversations/{conv.id}/messages",
            params={"page": 1, "page_size": 9999},
            headers=auth_headers,
        )
        data = response.json()
        # Should be capped at MAX_PAGE_SIZE (or at least not crash)
        assert data["page_size"] <= settings.MAX_PAGE_SIZE
        assert len(data["messages"]) <= settings.MAX_PAGE_SIZE


# ---------------------------------------------------------------------------
# Ownership Tests
# ---------------------------------------------------------------------------


class TestOwnership:
    """All endpoints enforce conversation ownership."""

    def test_get_messages_other_users_conversation(
        self,
        client: TestClient,
        auth_headers,
        other_conversation,
    ):
        """Getting messages from another user's conversation returns 403."""
        response = client.get(
            f"/api/v1/chat/conversations/{other_conversation.id}/messages",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_detail_other_users_conversation(
        self,
        client: TestClient,
        auth_headers,
        other_conversation,
    ):
        """Getting details of another user's conversation returns 403."""
        response = client.get(
            f"/api/v1/chat/conversations/{other_conversation.id}",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Conversation History Loading Tests
# ---------------------------------------------------------------------------


class TestConversationHistory:
    """Conversation history is loaded correctly for multi-turn context."""

    def test_load_history(
        self,
        db_session,
        conversation_with_messages,
        user,
    ):
        """History should return messages as {role, content} dicts."""
        conv, _ = conversation_with_messages
        from app.services.message_service import get_conversation_history

        history = get_conversation_history(
            db=db_session,
            conversation_id=conv.id,
            max_messages=10,
        )
        assert len(history) == 10  # 10 messages in the fixture
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "User message 1"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Assistant response 1"

    def test_history_respects_max_messages(
        self,
        db_session,
        conversation_with_messages,
    ):
        """History should be limited to max_messages."""
        conv, _ = conversation_with_messages
        from app.services.message_service import get_conversation_history

        history = get_conversation_history(
            db=db_session,
            conversation_id=conv.id,
            max_messages=4,
        )
        assert len(history) == 4

    def test_empty_conversation_returns_empty_history(
        self,
        db_session,
        conversation,
    ):
        """A conversation with no messages should return empty history."""
        from app.services.message_service import get_conversation_history

        history = get_conversation_history(
            db=db_session,
            conversation_id=conversation.id,
        )
        assert history == []


# ---------------------------------------------------------------------------
# Assistant Message Failed State Tests
# ---------------------------------------------------------------------------


class TestAssistantFailedPersistence:
    """When Gemini fails, the assistant message should be saved as FAILED."""

    def test_save_failed_assistant_message(
        self,
        db_session,
        conversation,
        user,
    ):
        """A failed assistant message should preserve error metadata."""
        from app.services.message_service import save_assistant_message

        msg = save_assistant_message(
            db=db_session,
            conversation_id=conversation.id,
            user_id=user.id,
            content="Gemini API quota exceeded",
            status=MessageStatus.FAILED,
            error_metadata={
                "error": "Gemini API quota exceeded",
                "latency_ms": 1234.56,
            },
        )
        assert msg.status == MessageStatus.FAILED
        assert msg.error_metadata["error"] == "Gemini API quota exceeded"
        assert msg.error_metadata["latency_ms"] == 1234.56

    def test_failed_message_included_in_history(
        self,
        db_session,
        conversation,
        user,
    ):
        """Failed messages should still appear in conversation history."""
        from app.services.message_service import save_assistant_message

        save_assistant_message(
            db=db_session,
            conversation_id=conversation.id,
            user_id=user.id,
            content="Sorry, an error occurred",
            status=MessageStatus.FAILED,
        )

        from app.services.message_service import get_conversation_history
        history = get_conversation_history(
            db=db_session,
            conversation_id=conversation.id,
        )
        assert len(history) == 1
        assert history[0]["role"] == "assistant"


# ---------------------------------------------------------------------------
# Auto-Title Generation Tests
# ---------------------------------------------------------------------------


class TestAutoTitle:
    """Conversation titles are auto-generated from the first user message."""

    def test_auto_title_short_message(self):
        """A short message should become the full title."""
        from app.services.conversation_service import auto_title_from_message

        title = auto_title_from_message("What is JWT authentication?")
        assert title == "What is JWT authentication?"

    def test_auto_title_truncates_long(self):
        """A long message should be truncated."""
        from app.services.conversation_service import auto_title_from_message

        long_msg = "x" * 200
        title = auto_title_from_message(long_msg, max_length=50)
        assert len(title) <= 53  # 50 chars + 3 for "..."
        assert title.endswith("...")

    def test_auto_title_uses_first_line(self):
        """Only the first line should be used for the title."""
        from app.services.conversation_service import auto_title_from_message

        multi_line = "First line is the title\nSecond line not included"
        title = auto_title_from_message(multi_line)
        assert "First line is the title" == title
        assert "Second line" not in title

    def test_auto_title_empty(self):
        """An empty message should return empty title."""
        from app.services.conversation_service import auto_title_from_message

        title = auto_title_from_message("")
        assert title == ""


# ---------------------------------------------------------------------------
# SSE Streaming Tests
# ---------------------------------------------------------------------------


class TestStreaming:
    """SSE streaming endpoint produces correct event types."""

    def test_stream_requires_auth(self, client: TestClient):
        """Unauthenticated stream request should be rejected."""
        response = client.post(
            "/api/v1/chat/stream",
            json={"question": "test question"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("app.api.v1.endpoints.chat.stream_answer")
    def test_stream_events_format(
        self,
        mock_stream_answer,
        client: TestClient,
        auth_headers,
    ):
        """Stream should produce token, citation, and done events."""
        conv_id = uuid.uuid4()
        msg_id = uuid.uuid4()

        def mock_stream():
            yield {"type": "citation", "citations": [{"document_id": str(uuid.uuid4()), "filename": "doc.pdf"}]}
            yield {"type": "token", "content": "Hello"}
            yield {"type": "token", "content": " world"}
            yield {
                "type": "done",
                "citations": [],
                "conversation_id": conv_id,
                "message_id": msg_id,
            }

        mock_stream_answer.return_value = mock_stream()

        with client.stream("POST", "/api/v1/chat/stream", json={"question": "test"}, headers=auth_headers) as response:
            assert response.status_code == status.HTTP_200_OK
            assert "text/event-stream" in response.headers["content-type"]

            events = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

        assert len(events) == 4
        assert events[0]["type"] == "citation"
        assert events[1]["type"] == "token"
        assert events[1]["content"] == "Hello"
        assert events[2]["type"] == "token"
        assert events[2]["content"] == " world"
        assert events[3]["type"] == "done"
        assert events[3]["conversation_id"] == str(conv_id)
        assert events[3]["message_id"] == str(msg_id)

    @patch("app.api.v1.endpoints.chat.stream_answer")
    def test_stream_error_event(
        self,
        mock_stream_answer,
        client: TestClient,
        auth_headers,
    ):
        """Stream should produce error event on failure."""
        mock_stream_answer.side_effect = Exception("Network error")

        with client.stream("POST", "/api/v1/chat/stream", json={"question": "test"}, headers=auth_headers) as response:
            events = []
            for line in response.iter_lines():
                if line and line.startswith("data: "):
                    events.append(json.loads(line[6:]))

        assert len(events) == 1
        assert events[0]["type"] == "error"

    @patch("app.api.v1.endpoints.chat.stream_answer")
    def test_stream_with_existing_conversation(
        self,
        mock_stream_answer,
        client: TestClient,
        auth_headers,
    ):
        """Stream should accept a conversation_id and pass it through."""
        conv_id = uuid.uuid4()

        def mock_stream():
            yield {"type": "token", "content": "Hello"}
            yield {
                "type": "done",
                "citations": [],
                "conversation_id": conv_id,
                "message_id": uuid.uuid4(),
            }

        mock_stream_answer.return_value = mock_stream()

        response = client.post(
            "/api/v1/chat/stream",
            json={"question": "test", "conversation_id": str(conv_id)},
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# RAG Service Stream Answer Tests
# ---------------------------------------------------------------------------


class TestStreamAnswer:
    """RAGService.stream_answer produces correct streaming behavior."""

    def test_stream_answer_no_results(
        self,
        db_session,
        user,
    ):
        """When no search results, stream should yield missing-context answer."""
        from app.services.rag_service import stream_answer

        with patch("app.services.rag_service._generate_query_embedding") as mock_embed:
            mock_embed.return_value = [0.1, 0.2, 0.3]
            with patch("app.services.rag_service.get_vector_service") as mock_vs:
                mock_vs_instance = MagicMock()
                mock_vs_instance.search.return_value = []
                mock_vs.return_value = mock_vs_instance

                generator = stream_answer(
                    db=db_session,
                    user_id=user.id,
                    question="test",
                )

                events = list(generator)
                token_events = [e for e in events if e["type"] == "token"]
                done_events = [e for e in events if e["type"] == "done"]

                assert len(token_events) >= 1
                assert "could not find enough information" in token_events[0]["content"]
                assert len(done_events) == 1

    def test_stream_answer_gemini_failure(
        self,
        db_session,
        user,
    ):
        """When Gemini fails during streaming, an error event is yielded and
        the assistant message is saved as FAILED."""

        from app.services.rag_service import stream_answer
        from app.schemas.chat import RetrievedChunk

        with patch("app.services.rag_service._generate_query_embedding") as mock_embed:
            mock_embed.return_value = [0.1, 0.2, 0.3]

            with patch("app.services.rag_service.get_vector_service") as mock_vs:
                mock_vs_instance = MagicMock()
                mock_vs_instance.search.return_value = [
                    {"chunk_id": str(uuid.uuid4()), "document_id": str(uuid.uuid4()), "score": 0.95}
                ]
                mock_vs.return_value = mock_vs_instance

                with patch("app.services.rag_service._pack_context") as mock_pack:
                    fake_chunk = RetrievedChunk(
                        chunk_id=uuid.uuid4(), document_id=uuid.uuid4(),
                        content="fake content", filename="test.pdf",
                        page=1, score=0.95,
                    )
                    mock_pack.return_value = ("fake context", [fake_chunk])

                    with patch("app.services.rag_service.gemini_stream_generate") as mock_gemini:
                        from app.services.llm_service import LLMError
                        mock_gemini.side_effect = LLMError("Quota exceeded")

                        generator = stream_answer(
                            db=db_session,
                            user_id=user.id,
                            question="test question",
                        )

                        events = list(generator)
                        error_events = [e for e in events if e["type"] == "error"]
                        assert len(error_events) >= 1
                        assert "error" in error_events[0]["detail"]

                        # Check the assistant message was saved as FAILED
                        from app.models.message import Message, MessageStatus
                        failed_msgs = (
                            db_session.query(Message)
                            .filter(
                                Message.conversation_id.isnot(None),
                                Message.role == MessageRole.ASSISTANT,
                                Message.status == MessageStatus.FAILED,
                            )
                            .all()
                        )
                        assert len(failed_msgs) >= 1

    def test_stream_answer_creates_conversation(
        self,
        db_session,
        user,
    ):
        """When no conversation_id provided, stream should create a new conversation."""
        from app.services.rag_service import stream_answer

        with patch("app.services.rag_service._generate_query_embedding") as mock_embed:
            mock_embed.return_value = [0.1, 0.2, 0.3]
            with patch("app.services.rag_service.get_vector_service") as mock_vs:
                mock_vs_instance = MagicMock()
                mock_vs_instance.search.return_value = []
                mock_vs.return_value = mock_vs_instance

                generator = stream_answer(
                    db=db_session,
                    user_id=user.id,
                    question="First ever question",
                )

                list(generator)

                # A conversation should have been created
                convs = (
                    db_session.query(Conversation)
                    .filter(Conversation.user_id == user.id)
                    .all()
                )
                assert len(convs) == 1
                # Title should be the first user message
                assert "First ever question" in convs[0].title

    def test_stream_answer_preserves_existing_conversation(
        self,
        db_session,
        user,
        conversation,
    ):
        """When conversation_id provided, stream should use the existing one."""
        from app.services.rag_service import stream_answer

        with patch("app.services.rag_service._generate_query_embedding") as mock_embed:
            mock_embed.return_value = [0.1, 0.2, 0.3]
            with patch("app.services.rag_service.get_vector_service") as mock_vs:
                mock_vs_instance = MagicMock()
                mock_vs_instance.search.return_value = []
                mock_vs.return_value = mock_vs_instance

                generator = stream_answer(
                    db=db_session,
                    user_id=user.id,
                    question="Another question",
                    conversation_id=conversation.id,
                )

                list(generator)

                # No new conversations should be created
                convs = (
                    db_session.query(Conversation)
                    .filter(Conversation.user_id == user.id)
                    .all()
                )
                assert len(convs) == 1


# ---------------------------------------------------------------------------
# Chat Settings Validation
# ---------------------------------------------------------------------------


class TestChatSettings:
    """Chat system configuration settings should exist with sensible defaults."""

    def test_chat_settings_exist(self):
        """Required chat settings should be present."""
        assert hasattr(settings, "MAX_HISTORY_MESSAGES")
        assert hasattr(settings, "DEFAULT_PAGE_SIZE")
        assert hasattr(settings, "MAX_PAGE_SIZE")
        assert hasattr(settings, "STREAM_TIMEOUT")
        assert hasattr(settings, "AUTO_TITLE_LENGTH")
        assert hasattr(settings, "CHAT_TIMEOUT_SECONDS")

    def test_chat_sensible_defaults(self):
        """Chat settings should have sensible default values."""
        assert settings.MAX_HISTORY_MESSAGES >= 2
        assert settings.DEFAULT_PAGE_SIZE >= 10
        assert settings.MAX_PAGE_SIZE >= settings.DEFAULT_PAGE_SIZE
        assert settings.AUTO_TITLE_LENGTH >= 30


# ---------------------------------------------------------------------------
# End-to-End Integration Tests
# ---------------------------------------------------------------------------


class TestChatE2E:
    """End-to-end chat flow — create conversation, send message,
    verify persistence, verify history loads."""

    def test_e2e_flow(
        self,
        client: TestClient,
        auth_headers,
    ):
        """Full end-to-end chat flow with mocked RAG."""

        # 1. Create a conversation
        create_resp = client.post(
            "/api/v1/chat/conversations",
            json={"title": "E2E Test"},
            headers=auth_headers,
        )
        assert create_resp.status_code == status.HTTP_201_CREATED
        conv_id = create_resp.json()["id"]

        # 2. List conversations and verify it appears
        list_resp = client.get(
            "/api/v1/chat/conversations",
            headers=auth_headers,
        )
        assert list_resp.status_code == status.HTTP_200_OK
        assert any(c["id"] == conv_id for c in list_resp.json()["conversations"])

        # 3. Get conversation detail (empty)
        get_resp = client.get(
            f"/api/v1/chat/conversations/{conv_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == status.HTTP_200_OK
        assert get_resp.json()["messages"] == []

        # 4. Send a question via ask endpoint — mock at the service layer
        from app.schemas.chat import RetrievedChunk

        with patch("app.services.rag_service._generate_query_embedding") as mock_embed:
            mock_embed.return_value = [0.1, 0.2, 0.3]
            with patch("app.services.rag_service.get_vector_service") as mock_vs:
                mock_vs_instance = MagicMock()
                mock_vs_instance.search.return_value = [
                    {"chunk_id": str(uuid.uuid4()), "document_id": str(uuid.uuid4()), "score": 0.95}
                ]
                mock_vs.return_value = mock_vs_instance
                with patch("app.services.rag_service._pack_context") as mock_pack:
                    fake_chunk = RetrievedChunk(
                        chunk_id=uuid.uuid4(), document_id=uuid.uuid4(),
                        content="fake content for e2e", filename="life.pdf",
                        page=1, score=0.95,
                    )
                    mock_pack.return_value = ("fake context", [fake_chunk])
                    with patch("app.services.rag_service.gemini_generate") as mock_gemini:
                        mock_gemini.return_value = {
                            "text": "42 is the meaning of life",
                            "prompt_tokens": 100,
                            "completion_tokens": 10,
                            "total_tokens": 110,
                            "latency_ms": 500,
                        }

                        ask_resp = client.post(
                            "/api/v1/chat/ask",
                            json={"question": "What is the meaning of life?", "conversation_id": conv_id},
                            headers=auth_headers,
                        )
                        assert ask_resp.status_code == status.HTTP_200_OK
                        assert "42" in ask_resp.json()["answer"]

        # 5. Get conversation detail again — should now have messages
        get_resp2 = client.get(
            f"/api/v1/chat/conversations/{conv_id}",
            headers=auth_headers,
        )
        assert get_resp2.status_code == status.HTTP_200_OK
        detail = get_resp2.json()
        assert detail["message_count"] >= 2  # user + assistant

        # 6. Rename conversation
        rename_resp = client.patch(
            f"/api/v1/chat/conversations/{conv_id}",
            json={"title": "Renamed E2E"},
            headers=auth_headers,
        )
        assert rename_resp.status_code == status.HTTP_200_OK
        assert rename_resp.json()["title"] == "Renamed E2E"

        # 7. Delete conversation
        delete_resp = client.delete(
            f"/api/v1/chat/conversations/{conv_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == status.HTTP_204_NO_CONTENT

        # 8. Verify deletion
        get_resp3 = client.get(
            f"/api/v1/chat/conversations/{conv_id}",
            headers=auth_headers,
        )
        assert get_resp3.status_code == status.HTTP_404_NOT_FOUND
