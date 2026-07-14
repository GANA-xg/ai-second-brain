# Chat System

The chat system provides conversational RAG (Retrieval-Augmented Generation) over a user's uploaded documents. It supports synchronous question-answering, token-by-token SSE streaming, conversation CRUD, pagination, and ownership enforcement.

---

## Architecture

```
User Request → Chat Endpoints → ConversationService / MessageService → RAG Pipeline → Gemini
                                                                          ↓
                                                                    Qdrant (vector search)
```

**Layers:**

| Layer | Module | Responsibility |
|---|---|---|
| API | `app/api/v1/endpoints/chat.py` | HTTP routing, request validation, error-to-status mapping |
| Service | `app/services/conversation_service.py` | Conversation CRUD + ownership checks |
| Service | `app/services/message_service.py` | Message persistence + pagination + history loading |
| Service | `app/services/rag_service.py` | Full RAG pipeline: embedding → search → context → Gemini → citations |
| Schemas | `app/schemas/chat.py` | Pydantic request/response models |
| Models | `app/models/conversation.py` | Conversation ORM model |
| Models | `app/models/message.py` | Message ORM model (USER / ASSISTANT roles) |

---

## Data Model

### Conversation

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `user_id` | UUID (FK → users) | Owner of the conversation |
| `title` | String(255) | User-set or auto-generated from first message |
| `created_at` | DateTime | Set on creation |
| `updated_at` | DateTime | Updated on each new message |
| `deleted_at` | DateTime? | Soft-delete timestamp |

### Message

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `conversation_id` | UUID (FK → conversations, CASCADE) | Parent conversation |
| `role` | Enum(USER / ASSISTANT / SYSTEM) | Message origin |
| `content` | Text | Message body |
| `status` | Enum(PENDING / COMPLETED / FAILED / CANCELLED) | Lifecycle status |
| `citations` | JSON | List of `{document_id, filename, chunk_id, page, score}` |
| `prompt_tokens` | Integer? | Token usage tracking |
| `completion_tokens` | Integer? | Token usage tracking |
| `total_tokens` | Integer? | Token usage tracking |
| `error_metadata` | JSON? | Error details for FAILED messages |
| `created_at` | DateTime | Set on creation |
| `updated_at` | DateTime | Updated on status change |
| `deleted_at` | DateTime? | Soft-delete timestamp |

**Index:** `ix_messages_conversation_created` on `(conversation_id, created_at)` for efficient ordered retrieval.

### Status Lifecycle

```
USER message:  immediately persisted (no status)
ASSISTANT:     PENDING → COMPLETED (success) or FAILED (error)
               or CANCELLED (client disconnect during streaming)
```

If the user message is the first in a conversation with the default title `"New conversation"`, the title is auto-generated from the message's first line (capped at `AUTO_TITLE_LENGTH` characters).

---

## Configuration

All chat settings live in `app.core.config.Settings`:

| Variable | Default | Description |
|---|---|---|
| `DEFAULT_PAGE_SIZE` | 20 | Messages per page by default |
| `MAX_PAGE_SIZE` | 100 | Hard cap on messages per page |
| `MAX_HISTORY_MESSAGES` | 6 | Last N messages injected as context into the RAG prompt |
| `AUTO_TITLE_LENGTH` | 95 | Max chars for auto-generated conversation titles |
| `CHAT_TIMEOUT_SECONDS` | 60 | Gemini timeout for synchronous `ask` |

---

## API Reference

All endpoints are prefixed with `/api/v1/chat`.

### Conversation CRUD

#### `POST /conversations`

Create a new conversation.

```json
// Request
{ "title": "My conversation" }  // title is optional

// Response (201)
{
  "id": "uuid",
  "title": "My conversation",
  "message_count": 0,
  "created_at": "2026-07-09T00:00:00Z",
  "updated_at": "2026-07-09T00:00:00Z"
}
```

#### `GET /conversations`

List conversations for the authenticated user. Ordered by `updated_at DESC`.

| Query param | Default | Description |
|---|---|---|
| `limit` | 50 | Max conversations to return (capped at `MAX_PAGE_SIZE`) |
| `offset` | 0 | Pagination offset |

Response (200):
```json
{
  "conversations": [
    {
      "id": "uuid",
      "title": "My conversation",
      "message_count": 3,
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 1
}
```

#### `GET /conversations/{conversation_id}`

Get a single conversation with paginated messages.

| Query param | Default | Description |
|---|---|---|
| `page` | 1 | Page number |
| `page_size` | `DEFAULT_PAGE_SIZE` (20) | Messages per page (capped at `MAX_PAGE_SIZE`) |

Response includes `page`, `page_size`, `has_next` for client-side pagination.

Errors: `404` (not found), `403` (wrong owner).

#### `PATCH /conversations/{conversation_id}`

Rename a conversation.

```json
// Request
{ "title": "New title" }
```

#### `DELETE /conversations/{conversation_id}`

Delete a conversation and all its messages (CASCADE). Returns `204 No Content`.

### Messages

#### `GET /conversations/{conversation_id}/messages`

Get paginated messages for a conversation (same pagination as above).

```json
// Response (200)
{
  "messages": [
    {
      "id": "uuid",
      "role": "USER",
      "content": "What is Q4 revenue?",
      "citations": null,
      "created_at": "..."
    },
    {
      "id": "uuid",
      "role": "ASSISTANT",
      "content": "Based on the uploaded documents...",
      "status": "COMPLETED",
      "citations": [
        {
          "document_id": "uuid",
          "filename": "q4-report.pdf",
          "chunk_id": "uuid",
          "page": 12,
          "score": 0.95
        }
      ],
      "prompt_tokens": 450,
      "completion_tokens": 120,
      "total_tokens": 570
    }
  ],
  "total": 2,
  "page": 1,
  "page_size": 20,
  "has_next": false
}
```

### Synchronous Question Answering

#### `POST /ask`

Ask a question and get a complete (non-streaming) answer.

```json
// Request
{
  "question": "What is the meaning of life?",
  "conversation_id": "uuid-or-null",
  "top_k": 10,            // optional, override
  "score_threshold": 0.0   // optional, override
}
```

```json
// Response (200)
{
  "answer": "42...",
  "citations": [
    {
      "document_id": "uuid",
      "filename": "life.pdf",
      "chunk_id": "uuid",
      "page": 1,
      "score": 0.95
    }
  ],
  "conversation_id": "uuid",
  "message_id": "uuid",
  "retrieved_chunks": [ ... ],
  "prompt_version": "v1",
  "model_used": "models/gemini-2.0-flash-lite"
}
```

Errors: `400` (RAG pipeline failure), `500` (internal server error).

### SSE Streaming (Server-Sent Events)

#### `POST /stream`

Stream the answer token-by-token over SSE.

**Request** (same body as `/ask`):

```json
{
  "question": "What is the meaning of life?",
  "conversation_id": "uuid-or-null"
}
```

**Response** is `text/event-stream` with `Cache-Control: no-cache`.

**Events** (each is `data: {...}\n\n`):

```json
// Token event
{ "type": "token", "content": "42" }

// Citation event (sent before first token)
{ "type": "citation", "citations": [...] }

// Done event
{
  "type": "done",
  "citations": [...],
  "conversation_id": "uuid",
  "message_id": "uuid"
}

// Error event
{ "type": "error", "detail": "...", "conversation_id": "uuid" }
```

**Flow on the server:**

1. User message is saved (PENDING)
2. Conversation history is loaded (last `MAX_HISTORY_MESSAGES` messages)
3. Query is embedded and Qdrant is searched (user-scoped)
4. Context is packed (dedup, ranking, token budget)
5. Citations are built and emitted
6. Gemini streams tokens
7. Assistant message is saved as COMPLETED
8. Done event with final metadata

On Gemini failure, the assistant message is saved as FAILED with error metadata.

---

## RAG Pipeline

The pipeline lives in `app/services/rag_service.py`:

```
ask_question(db, user_id, question, conversation_id?)
  │
  ├─ _get_or_create_conversation()
  ├─ save_user_message()
  ├─ _generate_query_embedding()
  ├─ _search_vector_db()          → Qdrant (top_k, score_threshold)
  ├─ _pack_context()              → dedup + token budget
  ├─ _build_citations()
  ├─ _build_prompt()              → prompt_service
  ├─ gemini_generate()            → Gemini API
  ├─ _store_messages()            → USER + ASSISTANT messages
  ├─ _store_retrieval_trace()
  └─ return ChatResponse(...)

stream_answer(db, user_id, question, conversation_id?)
  │  (same pipeline, but yields SSE events)
  ├─ save_user_message()
  ├─ yield "citation" event
  ├─ gemini_stream_generate()     → yields tokens
  ├─ _store_messages()            → on completion
  └─ yield "done" event
```

---

## Pagination

Both `GET /conversations/{id}` and `GET /conversations/{id}/messages` support pagination. The `page_size` parameter is always capped at `MAX_PAGE_SIZE` (100) to prevent abuse. The response includes `has_next: bool` so clients know whether to request the next page.

---

## Ownership & Security

- Every conversation and message endpoint verifies `current_user.id` matches `conversation.user_id`.
- Access violations return `403 Forbidden`; missing conversations return `404`.
- Qdrant searches are filtered by `user_id` to prevent cross-user document leakage.
- The streaming SSE endpoint has no special auth — it uses the same JWT-based `get_current_user` dependency.

---

## Token Budget

| Budget | Default | Config |
|---|---|---|
| Max context tokens for RAG prompt | 2000 | `settings.MAX_CONTEXT_TOKENS` |
| Max response tokens | 1024 | `settings.MAX_RESPONSE_TOKENS` |
| History messages injected | 6 | `settings.MAX_HISTORY_MESSAGES` |
| Page size cap | 100 | `settings.MAX_PAGE_SIZE` |

---

## Testing

The test suite (`tests/test_chat.py`) covers:

- **Conversation CRUD**: create, list, get, update, delete with ownership checks
- **Message persistence**: user message saved before AI call, assistant after
- **Pagination**: default page size, explicit page size, page_size capping
- **Streaming**: event format, token/citation/done/error events, Gemini failure handling
- **E2E flow**: full create → ask → verify messages → rename → delete lifecycle (all services mocked at the embedding/vector/Gemini layers)

Run tests:

```bash
cd backend
source venv/bin/activate
python -m pytest tests/test_chat.py -v --tb=short
```

See also `tests/test_rag.py` for RAG pipeline unit tests (30 tests covering context packing, citations, prompts, error handling, trace logging, config validation).

---

## Known Fixes

1. **JSON serialization of citations**: `Citation.model_dump()` returns raw `UUID` objects. The `_store_messages` function converts UUIDs to strings via `{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in ...}` before storing in the JSON column.
2. **Page size capping**: Applied both in the endpoint layer (`min(page_size, settings.MAX_PAGE_SIZE)`) and in `message_service.get_messages()` for defense-in-depth.
3. **Streaming error events**: Error events use `"type": "error"` as top-level discriminator (not nested keys), matching the `StreamEvent` schema.
