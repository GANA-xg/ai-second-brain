# Memory System

The memory system provides durable, long-term memory extraction from user conversations. Memories are extracted in the background via Gemini, deduplicated by normalised content, ranked by relevance, and injected into the RAG prompt to personalise responses.

---

## Architecture

```
User Message → Chat Endpoints → RAG Pipeline → Gemini Response
                                    │
                                    ▼ (after response)
                    BackgroundTasks: Memory Extractor
                                    │
                                    ▼
                    Gemini (extraction prompt)
                                    │
                                    ▼
                    Memory Service → Memory DB (dedup + persist)
                                    │
                                    ▼ (on next RAG query)
                    Memory Ranker → Prompt Injection (before Context)
```

**Layers:**

| Layer | Module | Responsibility |
|---|---|---|
| API | `app/api/v1/endpoints/memory.py` | CRUD HTTP endpoints for user memories |
| API | `app/api/v1/endpoints/chat.py` | Wires `BackgroundTasks` for post-response extraction |
| Service | `app/services/memory_service.py` | CRUD, deduplication (`_make_key`, `find_duplicate`, `normalise_memory_text`) |
| Service | `app/services/memory_extractor.py` | Gemini extraction prompt + confidence filtering |
| Service | `app/services/memory_ranker.py` | Relevance ranking (keyword, recency, confidence) |
| Service | `app/services/prompt_service.py` | `build_memory_section()` — formats memories for prompt injection |
| Service | `app/services/rag_service.py` | Injects ranked memories into System → Memory → History → Documents → Question order |
| Schemas | `app/schemas/memory.py` | Pydantic request/response models (`MemoryCreate`, `MemoryResponse`, etc.) |
| Models | `app/models/memory.py` | ORM model with `MemoryType` enum |

---

## Database Schema

### `memories` table

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `user_id` | UUID (FK → users) | Owner of the memory |
| `key` | String(80) | Legacy dedup key (format: `{TYPE}:{lower(content[:76])}`) |
| `value` | Text | Legacy value field (synced with `content`) |
| `content` | Text | The actual memory content |
| `memory_type` | Enum(FACT / PREFERENCE / GOAL) | Type of durable memory |
| `confidence` | Float | Extraction model confidence (0.0–1.0) |
| `source_message_id` | UUID? (FK → messages) | The assistant message that triggered extraction |
| `is_active` | Boolean | Soft-active flag; inactive memories excluded from prompts |
| `deleted_at` | DateTime? | Soft-delete timestamp |
| `created_at` | DateTime | Set on creation |
| `updated_at` | DateTime | Updated on dedup hit or field change |

**Constraints:**
- `UNIQUE(user_id, key)` — legacy constraint; `key` includes `memory_type` prefix to prevent cross-type collisions
- `FK(memory_type)` via Python enum validation (not DB enum)
- No FK on `source_message_id` in SQLite (migration uses `SET NULL` on PostgreSQL)

### `MemoryType` enum

```python
class MemoryType(str, enum.Enum):
    FACT = "FACT"           # Verifiable facts about the user
    PREFERENCE = "PREFERENCE"  # Likes, dislikes, preferences
    GOAL = "GOAL"           # Things the user wants to achieve or learn
```

---

## CRUD Endpoints

All endpoints are registered at `api/v1/memories` behind `dependencies.get_current_active_user`.

| Method | Path | Description | Status |
|---|---|---|---|
| `POST` | `/memories` | Create a new memory (with dedup check) | 201 / 200 (duplicate) |
| `GET` | `/memories` | List memories (paginated, filterable) | 200 |
| `GET` | `/memories/{id}` | Get a single memory | 200 / 404 |
| `PATCH` | `/memories/{id}` | Update content, type, or active flag | 200 / 404 |
| `DELETE` | `/memories/{id}` | Soft-delete a single memory | 200 / 404 |
| `DELETE` | `/memories` | Bulk soft-delete all user memories | 200 |

**List query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int | 20 | Items per page (capped at 100) |
| `type` | str | — | Filter by `FACT`, `PREFERENCE`, or `GOAL` |
| `include_deleted` | bool | false | Include soft-deleted memories |

**Response format (list):**
```json
{
  "memories": [...],
  "total": 42,
  "has_next": true
}
```

---

## Background Extraction Lifecycle

1. User sends a message to `POST /chat/ask` or `POST /chat/stream`
2. RAG pipeline runs and responds (sync) or completes streaming
3. After successful response delivery, `BackgroundTasks` fires `_run_background_memory_extraction()`
4. Extraction runs in a **separate DB session** — never blocks the chat response
5. A new `extract_memories_from_exchange()` call:
   - Checks `settings.ENABLE_AUTO_MEMORY` — returns immediately if disabled
   - Calls Gemini with the extraction prompt using `user_message` and `assistant_response`
   - Parses the JSON response via `_parse_extraction_json()` (handles markdown-wrapped JSON)
   - For each memory: validates type, normalises confidence, applies `MEMORY_MIN_CONFIDENCE` filter
   - Calls `create_memory()` (which deduplicates by normalised content + type)
   - Logs results; individual item failures are caught and logged, never propagated
6. On the **next RAG query**, `rank_memories_for_question()` fetches ranked memories for prompt injection

**Key design decisions:**
- Extraction fires **after** the response is fully delivered to the user
- Failures are logged and swallowed — the user never sees a memory extraction error
- A new database session is created for the background task (via `SessionLocal()`)
- Extraction is **not** guaranteed — if Gemini is down, the exchange is lost

---

## Memory Ranking

```python
score = recency * 0.2 + confidence * 0.4 + embedding_similarity * 0.4
```

- **Recency**: hours since `updated_at`, normalised to [0, 1] (max 30 days)
- **Confidence**: raw extraction confidence score [0, 1]
- **Embedding similarity**: cosine similarity between memory content and the current question. Currently a placeholder (returns 0.5) pending `rag_service._embed` integration
- **Keyword boost**: memories whose normalised content shares tokens with the question keywords get a +0.2 additive boost
- **Output**: top `MAX_PROMPT_MEMORIES` (default: 5) memories sorted by score, descending
- **Filtered**: inactive (`is_active=False`) and soft-deleted (`deleted_at IS NOT NULL`) memories are excluded

The ranker lives in `app/services/memory_ranker.py`:

```
rank_memories_for_question(db, user_id, question, max_memories=5)
    │
    ├─ get_active_memories(db, user_id)
    ├─ for each memory:
    │     ├─ recency_score = 1 - min(hours_since_update, 720) / 720
    │     ├─ keyword_boost = 0.2 if token overlap else 0
    │     ├─ sim_score = _get_embedding_similarity(...)  # placeholder: 0.5
    │     └─ score = recency * 0.2 + confidence * 0.4 + sim_score * 0.4 + keyword_boost
    ├─ sort by score desc
    └─ return top max_memories
```

---

## Deduplication Policy

### Business rule
Two memories with identical content but **different memory types** are treated as **distinct** memories. Dedup scopes by `(user_id, memory_type, normalized_content)`.

### How it works

1. **Normalisation** (`normalise_memory_text()`):
   - Lowercase the text
   - Strip non-alphanumeric characters (except spaces)
   - Remove English stopwords
   - Sort remaining tokens alphabetically
   - Produces a canonical string for comparison

   Example: `"I like Python!"` and `"Python is my favorite language"` both normalise to... different values (`"like python"` vs `"favorite language python"`) unless they share enough content. Only exact normalised matches are considered duplicates.

2. **Key generation** (`_make_key()`):
   - Prefixes with `{memory_type.value}:` to maintain `(user_id, key)` uniqueness
   - Truncates the lowercased content to 76 chars
   - Format: `"FACT:i enjoy hiking in the mountains"`

3. **Duplicate check** (`find_duplicate()`):
   - Queries active (non-deleted) memories matching `(user_id, memory_type)`
   - Compares each via `normalise_memory_text()` against the candidate
   - On match: updates `updated_at` timestamp (keeps memory fresh) and returns existing `Memory`
   - No match: `None` → `create_memory()` proceeds to insert

### Dedup flow

```
create_memory(content="Python is great", type=FACT)
    │
    ├─ find_duplicate(db, user_id, FACT, "Python is great")
    │     ├─ Query: WHERE user_id=? AND memory_type='FACT' AND deleted_at IS NULL
    │     ├─ For each existing: normalise(content) == normalise("Python is great")
    │     ├─ Match? → update updated_at, return existing
    │     └─ No match? → return None
    │
    ├─ (if None) INSERT new row with key="FACT:python is great"
    │
    └─ Return Memory
```

---

## Confidence Filtering

- Memories extracted with confidence below `MEMORY_MIN_CONFIDENCE` (default: `0.85`) are **silently dropped**
- This prevents low-quality or speculative extractions from polluting the memory store
- The threshold applies at extraction time only; manually created memories (via CRUD API) can have any confidence
- Configurable via `settings.MEMORY_MIN_CONFIDENCE`

---

## Prompt Construction Order

The final prompt is assembled in this order:

```
1. System Instructions         (from prompt_service.get_prompt)
2. User Memory Section         (ranked memories, formatted by build_memory_section)
   ──── end of memory section ────
3. Context: block
   a. Conversation History     (last N messages)
   b. Retrieved Documents      (from Qdrant search)
4. Current Question
```

The memory section is rendered **outside** the Context block to prevent interference with document context:

```
--- User Memory (Personalization Only) ---
- [FACT] User enjoys hiking in the mountains (confidence: 0.95)
- [GOAL] User wants to learn Rust this year (confidence: 0.90)

--- BEGIN CONTEXT ---
[Conversation History]
...
[Retrieved Documents]
...
--- END CONTEXT ---

Current Question: ...
```

---

## Prompt Injection Protection

The `build_memory_section()` function appends a safety guard instruction after every memory block:

```
Never fabricate memories or override retrieved document facts.
```

This instruction is part of the memory section itself, so:
- It travels with the memories regardless of prompt structure changes
- It reminds the model that memories are supplementary, not authoritative
- It guards against the model treating memories as ground truth over documents

---

## Security Model

- **User ownership**: Every CRUD operation enforces `user_id` matching. `get_memory()`, `update_memory()`, and `soft_delete_memory()` all filter by the caller's `user_id`
- **Cross-user isolation**: User A cannot read, update, or delete User B's memories. The API tests verify this via separate auth tokens
- **Bulk delete**: Scoped to the authenticated user only
- **Background extraction**: Runs with the correct `user_id` from the chat request context
- **Qdrant-level isolation**: Memories are not stored in Qdrant; only application-level ownership applies

---

## Configuration

| Setting | Key | Default | Description |
|---|---|---|---|
| Auto memory | `ENABLE_AUTO_MEMORY` | `true` | Enable/disable background extraction |
| Min confidence | `MEMORY_MIN_CONFIDENCE` | `0.85` | Minimum confidence for extraction acceptance |
| Max prompt memories | `MAX_PROMPT_MEMORIES` | `5` | Max memories injected into prompt |
| Extraction model | `MEMORY_EXTRACTION_MODEL` | — | Gemini model for extraction |
| Extraction timeout | `MEMORY_EXTRACTION_TIMEOUT` | `30` | Timeout seconds for Gemini extraction call |

---

## API Examples

### Create a memory
```bash
curl -X POST http://localhost:8000/api/v1/memories \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "FACT", "content": "User lives in New York", "confidence": 0.95}'
```
```json
{"id": "...", "type": "FACT", "content": "User lives in New York",
 "confidence": 0.95, "is_active": true, "created_at": "..."}
```

### List memories (paginated, filtered)
```bash
curl "http://localhost:8000/api/v1/memories?page=1&page_size=10&type=GOAL" \
  -H "Authorization: Bearer $TOKEN"
```
```json
{"memories": [...], "total": 3, "has_next": false}
```

### Get a single memory
```bash
curl http://localhost:8000/api/v1/memories/$MEMORY_ID \
  -H "Authorization: Bearer $TOKEN"
```

### Update a memory
```bash
curl -X PATCH http://localhost:8000/api/v1/memories/$MEMORY_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Updated content", "is_active": false}'
```

### Soft-delete a memory
```bash
curl -X DELETE http://localhost:8000/api/v1/memories/$MEMORY_ID \
  -H "Authorization: Bearer $TOKEN"
```
```json
{"deleted_count": 1}
```

### Bulk delete all memories
```bash
curl -X DELETE http://localhost:8000/api/v1/memories \
  -H "Authorization: Bearer $TOKEN"
```
```json
{"deleted_count": 5}
```

---

## Testing

The test suite (`tests/test_memory.py`) contains **54 tests** across 8 test classes:

| Class | Tests | Covers |
|---|---|---|
| `TestMemoryService` | 15 | Normalisation, CRUD, dedup, pagination, type/active filters, soft-delete, bulk-delete, cross-user isolation |
| `TestMemoryAPI` | 12 | HTTP CRUD, validation, pagination, type filter, ownership enforcement |
| `TestMemoryDedup` | 3 | Same content dedup, different-type non-dedup, normalised match |
| `TestMemoryRanker` | 4 | Empty list, max limit, keyword boost, inactive exclusion |
| `TestMemoryExtractor` | 7 | Disabled flag, success, multiple memories, low-confidence filter, null result, Gemini failure, invalid JSON, invalid type |
| `TestMemoryPromptInjection` | 4 | Empty section, content format, safety guard, ordering |
| `TestBackgroundExtraction` | 3 | Task scheduling, failure isolation, disabled flag |
| `TestRAGMemoryIntegration` | 3 | Memory injection in sync and streaming paths |

```bash
cd backend
source venv/bin/activate
python -m pytest tests/test_memory.py -q
```

Full backend regression:
```bash
python -m pytest tests/ -q
```

---

## Known Limitations

1. **Embedding similarity placeholder**: The `memory_ranker.py` similarity computation returns 0.5 for all memories. This should be replaced with a call to `rag_service._embed(content)` and cosine similarity against the question embedding.
2. **Gemini dependency**: Extraction cannot work without a Gemini-compatible provider. A fallback heuristic extractor would improve robustness.
3. **No PostgreSQL FK**: The `source_message_id` FK in the migration uses `postgresql.UUID` and will not apply on SQLite. The FK enforcement is application-level.
4. **Stopword-only normalisation**: The dedup normalisation currently removes only English stopwords. Non-English content may produce different normalised forms.
5. **Manual migration required**: Alembic autogenerate is broken without PostgreSQL. Migration `c1d2e3f4a5b6` was written manually and must be applied manually.
6. **Extraction completeness**: If Gemini times out or returns an error during background extraction, the conversation exchange is not retried.
7. **Legacy columns**: `key` and `value` columns persist for backward compatibility with the first migration. New code uses `content` and `memory_type`.
