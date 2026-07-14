# Flashcard System

> Part 12 of the AI Second Brain project — automated flashcard generation
> from document chunks using Gemini, with full CRUD and ownership enforcement.

## Overview

The flashcard system generates study flashcards from processed document chunks
using Gemini. It follows the same architectural patterns as the rest of the
codebase: FastAPI endpoints backed by a service layer, SQLAlchemy ORM models,
Pydantic v2 schemas, and Alembic migrations.

**Key capabilities:**

- Generate 3–8 flashcards per batch of 5 chunks via Gemini
- List flashcards with optional `document_id` filter and cursor-free pagination
- Update front/back text of individual flashcards
- Soft-delete individual flashcards or bulk-delete by document
- Every operation enforces user ownership (`flashcard.user_id == current_user.id`)
- No HTTP 500 on Gemini failure — gracefully returns 201 with zero cards
- Cache invalidation on create

## Files

| File | Purpose |
|---|---|
| `app/models/flashcard.py` | SQLAlchemy model with soft delete, difficulty enum, source chunk FK |
| `app/schemas/flashcard.py` | Pydantic v2 request/response schemas |
| `app/services/flashcard_service.py` | Business logic: generation pipeline, CRUD, JSON cleaning |
| `app/services/prompt_service.py` | `FLASHCARD_SYSTEM_INSTRUCTION` and `format_flashcard_prompt()` |
| `app/api/v1/endpoints/flashcards.py` | 5 REST endpoints |
| `app/core/config.py` | 4 flashcard-specific settings |
| `alembic/versions/f1a2b3c4d5e6_add_source_chunk_id_and_difficulty_to_flashcards.py` | Migration adding `difficulty` + `source_chunk_id` |
| `tests/test_flashcards.py` | 62 tests (61 pass, 1 skipped) |

## Data Model

### `Flashcard` (table: `flashcards`)

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID | PK, auto-generated |
| `user_id` | UUID (FK → users.id) | NOT NULL, indexed, CASCADE delete |
| `document_id` | UUID (FK → documents.id) | NOT NULL, indexed, CASCADE delete |
| `source_chunk_id` | UUID (FK → chunks.id) | NULLABLE, indexed, SET NULL on delete |
| `question` | TEXT | NOT NULL |
| `answer` | TEXT | NOT NULL |
| `difficulty` | ENUM (EASY/MEDIUM/HARD) | NOT NULL, indexed, default MEDIUM |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `updated_at` | TIMESTAMPTZ | NOT NULL |
| `deleted_at` | TIMESTAMPTZ | NULL (soft delete marker) |

### `FlashcardDifficulty` enum

- `EASY`, `MEDIUM`, `HARD`

## API Endpoints

All endpoints require authentication via Bearer JWT token.

### `POST /api/v1/documents/{document_id}/flashcards/generate`

Generate flashcards from a document's chunks.

- **Status:** 201 Created
- **Requires:** Document must exist, belong to user, and have status `PROCESSED`
- **Response:** `FlashcardGenerateResponse` — `message`, `generated_count`, `discarded_count`, `total_count`
- **Notes:** Gemini failure → 201 with zero cards (not 500). Empty-chunk document → 0 cards.

### `GET /api/v1/flashcards`

List flashcards for the authenticated user.

- **Query params:** `document_id` (optional UUID filter), `page` (default 1), `page_size` (default 20, max 100)
- **Response:** `FlashcardListResponse` — `flashcards[]`, `total`, `page`, `page_size`, `has_next`
- **Notes:** Excludes soft-deleted cards. Purely user-scoped; cross-user listing returns empty.

### `PATCH /api/v1/flashcards/{flashcard_id}`

Update a flashcard's front and/or back text.

- **Body:** `FlashcardUpdate` — `front` (optional, min 1 char), `back` (optional, min 1 char)
- **Response:** `FlashcardResponse` — full card with `front`/`back` fields
- **Notes:** Ownership enforced (404 if not found or not owned). Blank text rejected (422).

### `DELETE /api/v1/flashcards/{flashcard_id}`

Soft-delete a flashcard.

- **Status:** 204 No Content
- **Notes:** Ownership enforced (404). Sets `deleted_at` timestamp; record stays in DB.

### `DELETE /api/v1/documents/{document_id}/flashcards`

Bulk soft-delete all flashcards for a document.

- **Response:** `FlashcardDeleteResponse` — `detail`, `deleted_count`
- **Notes:** Ownership enforced (404). Only non-deleted cards are counted.

## Generation Pipeline

```
User request
    │
    ▼
1. Verify document EXISTS and belongs to user
    │
    ▼
2. Verify document status == PROCESSED
    │
    ▼
3. Load all chunks ORDER BY chunk_index
    │
    ▼
4. Batch chunks (default: 5 per batch)
    │
    ▼
5. For each batch:
    ├─ Combine chunk text with [Chunk N] prefix
    ├─ Call Gemini with flashcard prompt + system instruction
    ├─ Parse JSON response (strips code fences, trailing noise)
    ├─ Validate each card (non-empty front/back)
    └─ Store valid cards with MEDIUM difficulty & source_chunk_id
    │
    ▼
6. Invalidate search cache
    │
    ▼
Return statistics
```

### Gemini response cleaning

The `clean_gemini_response()` function handles real-world Gemini output:

1. Strips ```json / ``` code fences
2. Finds first `[` or `{` character, discarding leading text
3. Finds last `]` or `}` character, discarding trailing text
4. Falls back to `json.loads()` with graceful error logging

Both `front`/`back` and `question`/`answer` JSON keys are accepted and
normalized to `front`/`back` in storage.

### Batching

- `FLASHCARD_BATCH_SIZE` (default: 5) chunks per Gemini request
- `FLASHCARD_MAX_PER_BATCH` (default: 8) maximum cards per batch
- `FLASHCARD_MODEL` overrideable via settings
- `FLASHCARD_TIMEOUT_SECONDS` (default: 60) per Gemini call

## Configuration

| Setting | Default | Description |
|---|---|---|
| `FLASHCARD_BATCH_SIZE` | 5 | Chunks per Gemini batch |
| `FLASHCARD_MAX_PER_BATCH` | 8 | Max cards generated per batch |
| `FLASHCARD_MODEL` | `models/gemini-2.0-flash-lite` | Gemini model for generation |
| `FLASHCARD_TIMEOUT_SECONDS` | 60 | Per-request timeout for Gemini |

## Error Handling

All errors follow existing project patterns:

- **400:** Document not in PROCESSED status
- **404:** Document or flashcard not found (or not owned — ownership ambiguity resolved to 404 for security)
- **422:** Invalid input (blank text, out-of-range pagination)
- **500 (suppressed):** Gemini failures → 201 with zero cards, error logged

Cross-user access is always prevented — every query filters by `user_id`.

## Caching

The flashcard CRUD endpoints **do not** implement a dedicated cache layer.
However, the generation endpoint calls `invalidate_search_cache(user_id)` after
storing cards so that search results remain consistent.

If caching is desired, the recommended cache keys are:

- `flashcards:{user_id}:{document_id}` (list, TTL 120s)
- `flashcard:{flashcard_id}` (single item, TTL 120s)

## Test Coverage

61 tests covering:

- **Generation:** success, no chunks, empty document, cross-user, output cleaning
  (code fences, trailing text, leading text, nested), too-short response, invalid
  JSON, non-list response, Gemini timeout, Gemini failure, Gemini empty response
- **CRUD:** list (empty, with cards, pagination, cross-user, response field shape),
  update (success, partial, cross-user, empty front, not found), single delete
  (success, not found, cross-user), bulk delete by document (success, cross-user)
- **API:** unauthenticated access on all 5 endpoints, field validators
- **Models:** `FlashcardResponse` serialization from ORM

## Migration

The migration `f1a2b3c4d5e6` adds two columns to the existing `flashcards` table:

```sql
ALTER TABLE flashcards ADD COLUMN difficulty VARCHAR NOT NULL DEFAULT 'MEDIUM';
ALTER TABLE flashcards ADD COLUMN source_chunk_id UUID REFERENCES chunks(id);
CREATE INDEX ix_flashcards_difficulty ON flashcards(difficulty);
CREATE INDEX ix_flashcards_source_chunk_id ON flashcards(source_chunk_id);
```

Migration chain: `acdd6d7a468c` → `c1d2e3f4a5b6` → `f1a2b3c4d5e6`

To apply:

```bash
cd backend
alembic upgrade head
```
