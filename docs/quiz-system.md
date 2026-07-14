# Quiz System

The quiz system generates educational quiz questions from a user's document chunks via Gemini. It supports three question types (multiple choice, true/false, short answer), server-side scoring, attempt lifecycle with review mode, pagination, and ownership enforcement. All endpoints follow the same patterns established by the flashcard system (Part 12) and the broader AI Second Brain architecture.

---

## Architecture

```
User Request → Quiz Endpoints → QuizService → Gemini (per batch of chunks)
                                                  │
                                                  ▼
                                          JSON Validation + Parser
                                                  │
                                                  ▼
                                          QuizQuestion DB (persist)
                                                  │
                                                  ▼
                                          Quiz + QuizAttempt DB (scoring)
```

**Layers:**

| Layer | Module | Responsibility |
|---|---|---|
| API | `app/api/v1/endpoints/quiz.py` | HTTP routing, request validation, error-to-status mapping |
| Service | `app/services/quiz_service.py` | Generation pipeline, CRUD, scoring, attempt lifecycle |
| Prompts | `app/services/prompt_service.py` | Quiz system instruction, generation prompt builder, review prompt builder |
| Schemas | `app/schemas/quiz.py` | Pydantic v2 request/response models with JSON-string option decoding |
| Models | `app/models/quiz.py` | Quiz ORM model |
| Models | `app/models/quiz_question.py` | QuizQuestion ORM model (per-question row) |
| Models | `app/models/quiz_attempt.py` | QuizAttempt ORM model (answers + score) |
| Cache | `app/core/cache_keys.py`, `app/services/cache_service.py` | Cache-key helpers + invalidation |
| Config | `app/core/config.py` | Batch size, model, timeout, max-questions settings |

---

## Database Schema

### `quizzes` table

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `user_id` | UUID (FK → users) | Owner of the quiz |
| `document_id` | UUID (FK → documents) | Source document |
| `title` | String(255) | Quiz title |
| `total_questions` | Integer | Number of generated questions |
| `deleted_at` | DateTime? | Soft-delete timestamp |
| `created_at` | DateTime | Set on creation |
| `updated_at` | DateTime | Updated on any change |

**Constraints:**
- `FK(user_id → users.id)` — cascading delete
- `FK(document_id → documents.id)` — cascading delete
- `CK(total_questions >= 0)`
- `INDEX(user_id, created_at)` — paginated listing

### `quiz_questions` table

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `quiz_id` | UUID (FK → quizzes) | Parent quiz (CASCADE) |
| `source_chunk_id` | UUID? (FK → chunks) | Provenance: which chunk produced this question |
| `question_type` | String(20) | `multiple_choice`, `true_false`, or `short_answer` |
| `question_text` | Text | The question body |
| `options` | Text? | JSON-encoded list of options (MCQ only) |
| `correct_answer` | Text | The correct answer string |
| `explanation` | Text? | Explanation of the correct answer |
| `order_index` | Integer | Display ordering within the quiz |
| `difficulty` | String(20) | `easy`, `medium`, or `hard` |
| `deleted_at` | DateTime? | Soft-delete timestamp |
| `created_at` | DateTime | Set on creation |
| `updated_at` | DateTime | Updated on any change |

**Constraints:**
- `FK(quiz_id → quizzes.id)` — cascading delete
- `FK(source_chunk_id → chunks.id)` — `SET NULL` on chunk delete
- `INDEX(quiz_id)`
- `INDEX(source_chunk_id)`

### `quiz_attempts` table

| Column | Type | Description |
|---|---|---|
| `id` | UUID (PK) | Auto-generated |
| `quiz_id` | UUID (FK → quizzes) | The quiz being attempted (CASCADE) |
| `user_id` | UUID (FK → users) | The user who submitted the attempt |
| `answers` | Text? | JSON-encoded list of `{question_id, answer}` objects |
| `score` | Integer | Calculated percentage score (0–100) |
| `total_questions` | Integer | Number of questions in this attempt |
| `correct_answers` | Integer | Count of correctly answered questions |
| `completed_at` | DateTime? | Timestamp when the attempt was graded |
| `deleted_at` | DateTime? | Soft-delete timestamp |
| `created_at` | DateTime | Set on creation |
| `updated_at` | DateTime | Updated on any change |

**Constraints:**
- `FK(quiz_id → quizzes.id)` — cascading delete
- `FK(user_id → users.id)` — cascading delete
- `CK(score >= 0)`
- `CK(total_questions > 0)`
- `INDEX(quiz_id, created_at)`
- `INDEX(user_id)`

---

## Quiz Generation Pipeline

The generation pipeline processes document chunks in batches and persists validated questions.

1. **Document Verification** — Verify the document exists, belongs to the current user, and has status `PROCESSED`. Returns 404/400 on failure.
2. **Chunk Loading** — Load all chunks for the document, ordered by `chunk_index`.
3. **Chunk Batching** — Group chunks into batches of `QUIZ_BATCH_SIZE` (default: 5). Each batch produces at most `QUIZ_MAX_PER_BATCH` (default: 8) questions.
4. **Gemini Invocation** — For each batch, build a prompt via `format_quiz_prompt()` and call `gemini_generate()` with the configured `QUIZ_MODEL`.
5. **JSON Cleaning** — Strip markdown code fences, leading/trailing text, and extraneous whitespace via `clean_gemini_response()`.
6. **JSON Parsing** — Parse the cleaned string as JSON via `parse_quiz_json()`. Handles single-object and array formats. Returns empty list on parse failure.
7. **Question Validation** — Validate each question via `validate_question()`:
   - **MCQ**: Must have exactly 4 non-empty string options. `correct_answer` must be one of the options.
   - **True/False**: `correct_answer` must be non-empty.
   - **Short Answer**: `correct_answer` must be non-empty.
   - All types: `question_text` must be non-empty, `explanation` must be non-empty.
8. **Persistence** — Create a `Quiz` row, then a `QuizQuestion` row per validated question. Link each question to its source chunk (`source_chunk_id`).
9. **Cache Invalidation** — Invalidate `quiz:{user_id}:*` pattern in Redis.
10. **Result** — Return `QuizGenerateResponse` with `quiz_id`, `total_questions`, and `discarded_count`. Returns empty result (no quiz created) if no valid questions were generated.

### Generation Flow Diagram

```
POST /documents/{id}/quizzes/generate
    │
    ├─ Verify document exists + belongs to user + is PROCESSED
    ├─ Load chunks (ordered by chunk_index)
    ├─ Batch chunks (size = QUIZ_BATCH_SIZE)
    │
    ├─ For each batch:
    │   ├─ Build prompt via format_quiz_prompt(batch_text, question_count)
    │   ├─ gemini_generate(model=QUIZ_MODEL)
    │   ├─ clean_gemini_response() – strip fences
    │   ├─ parse_quiz_json() – parse to dict list
    │   ├─ validate_question() each item → keep/discard
    │   └─ Persist validated questions to DB
    │
    ├─ Create Quiz + QuizQuestion rows
    ├─ invalidate_quiz_cache(user_id)
    └─ Return QuizGenerateResponse
```

---

## Prompt Format

### System Instruction

```
You are a quiz generator. You create educational quiz questions from document
content. You output ONLY valid JSON with no markdown formatting, no code fences,
no explanations outside the JSON structure, and no conversational text.
```

### Generation Prompt (`format_quiz_prompt`)

```
Generate {question_count} quiz questions from the following document content.
Include a mix of question types:
- multiple_choice (exactly 4 options, correct answer in list)
- true_false (true/false statement)
- short_answer (open-ended, case-insensitive comparison)

Return ONLY valid JSON. No markdown. No code fences. No extra text.

Document content:
{chunk_text}

Required JSON format:
[
  {{
    "type": "multiple_choice",
    "question": "Question text",
    "options": ["A. Option 1", "B. Option 2", "C. Option 3", "D. Option 4"],
    "correct_answer": "B",
    "explanation": "Why B is correct"
  }},
  {{
    "type": "true_false",
    "question": "Statement to judge",
    "correct_answer": "True",
    "explanation": "Why this is true"
  }},
  {{
    "type": "short_answer",
    "question": "Open-ended question",
    "correct_answer": "Expected answer",
    "explanation": "Detailed explanation"
  }}
]
```

### Review Prompt (`format_quiz_review_prompt`)

```
Generate {question_count} ADDITIONAL quiz questions from the following content.
Do NOT duplicate the existing questions shown below. Focus on different concepts
and difficulty levels.

Existing questions:
{existing_questions_text}

Document content:
{chunk_text}

Return ONLY valid JSON following the same format.
```

---

## JSON Validation Strategy

### `clean_gemini_response()`

Strips markdown code fences and surrounding text from Gemini output:

- Removes leading ````json` or ````\n` fences
- Removes trailing ````\n` fences
- Removes any text before the first `[` or `{` character
- Removes any text after the last `]` or `}` character
- Strips leading/trailing whitespace

### `parse_quiz_json()`

Parses the cleaned Gemini response into a list of dictionaries:

1. Attempts `json.loads()` on the cleaned text.
2. If the result is a single dict (not a list), wraps it in a list.
3. Returns an empty list on any parse failure (never raises).

### `validate_question()`

Validates a single question dictionary. Returns the validated dict or `None`:

| Condition | MCQ | True/False | Short Answer |
|---|---|---|---|
| `question` must be non-empty | ✓ | ✓ | ✓ |
| `correct_answer` must be non-empty | ✓ | ✓ | ✓ |
| `explanation` must be non-empty | ✓ | ✓ | ✓ |
| `options` must be list of 4 non-empty strings | ✓ | N/A | N/A |
| `type` must be recognised | ✓ | ✓ | ✓ |

**Returns:** the validated dictionary with trimmed strings and `options` set to `None` for non-MCQ types, or `None` if any validation check fails.

---

## Parsing Strategy

The parsing pipeline is forgiving by design — no Gemini output issue should cause a 500 error:

1. **Fence stripping** — Removes both ` ```json ` and ` ``` ` (no language tag) code fences.
2. **Extraneous text removal** — Strips all text before the first `[`/`{` and after the last `]`/`}`.
3. **JSON parse** — Standard `json.loads()` on the cleaned body.
4. **Single-object wrapping** — If the result is a dict, wraps it in a list so downstream code always iterates a list.
5. **Empty fallback** — Any failure at any step returns `[]` and logs a warning. The batch continues, and the quiz is created with whatever valid questions survive.

---

## Chunk Batching

Chunks from a document are grouped into batches to fit within Gemini context limits:

- **Batch size**: `QUIZ_BATCH_SIZE = 5` (configurable via `settings.QUIZ_BATCH_SIZE`)
- **Max questions per batch**: `QUIZ_MAX_PER_BATCH = 8`
- **Max total questions per quiz**: `QUIZ_MAX_QUESTIONS = 50`
- **Default question count per batch**: `QUIZ_DEFAULT_QUESTION_COUNT = 5`

```python
def batch_chunks(chunks, batch_size=QUIZ_BATCH_SIZE):
    """Group chunks into batches of batch_size."""
    return [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]
```

Each batch produces a separate Gemini call. If one batch fails (Gemini error, invalid JSON), the other batches continue processing independently. The quiz is created with whatever questions survived across all batches.

---

## CRUD Endpoints

All endpoints are registered under `/api/v1` behind `dependencies.get_current_active_user`.

| Method | Path | Description | Status |
|---|---|---|---|
| `POST` | `/documents/{id}/quizzes/generate` | Generate a quiz from a document's chunks | 201 / 400 / 404 |
| `GET` | `/quizzes` | List quizzes (paginated, filterable by `document_id`) | 200 |
| `GET` | `/quizzes/{id}` | Get a quiz with all questions | 200 / 404 |
| `DELETE` | `/quizzes/{id}` | Soft-delete a quiz | 204 / 404 |
| `DELETE` | `/documents/{id}/quizzes` | Soft-delete all quizzes for a document | 204 |
| `POST` | `/quizzes/{id}/attempt` | Submit a quiz attempt | 201 / 400 / 404 |
| `GET` | `/quizzes/{id}/attempts` | List attempts (paginated) | 200 / 404 |
| `GET` | `/quizzes/{id}/attempts/{attempt_id}` | Get a specific attempt with review results | 200 / 404 |

**List query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `page` | int ≥ 1 | 1 | Page number |
| `page_size` | int (1–100) | 20 | Items per page |
| `document_id` | UUID? | None | Filter by source document |

**Generate query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `question_count` | int (1–20) | 5 | Target question count per batch |

**Response shapes:**

`GET /quizzes/{id}` returns `QuizResponse` with nested `questions` array including `correct_answer` and `explanation` for each question (owner view).

---

## Attempt Lifecycle

```
POST /quizzes/{id}/attempt
    │
    ├─ Verify quiz exists + belongs to user → 404
    ├─ Load questions for quiz
    ├─ If no questions → 400
    ├─ For each submitted answer:
    │   ├─ Find matching question by question_id
    │   ├─ _is_answer_correct(user_answer, correct_answer, question_type)
    │   └─ Track correct/incorrect
    ├─ Calculate score = round(correct_answers / total_questions * 100)
    ├─ Persist QuizAttempt with answers JSON, score, correct_answers
    ├─ Set completed_at = UTC now
    ├─ invalidate_quiz_cache(user_id)
    └─ Return QuizAttemptResponse with score + per-question results
```

### Key Behaviours

- **Authentication**: Every endpoint requires a valid JWT with `current_user.id`.
- **Ownership enforcement**: All operations check `quiz.user_id == current_user.id`. Cross-user access returns 404 (not 403) to avoid leaking existence information.
- **Retry allowed**: Users can submit multiple attempts on the same quiz. Each attempt is independently scored and persisted.
- **Empty quiz**: If a quiz has zero questions, submitting an attempt returns 400.
- **Answer format**: `[{question_id: UUID, answer: string}]` as a raw JSON body (not nested under an object key).
- **Completed at**: Set to `datetime.utcnow()` after scoring, indicating the attempt is finalised.

---

## Scoring Algorithm

```python
def calculate_score(correct_answers: int, total_questions: int) -> int:
    """Calculate percentage score rounded to nearest integer."""
    if total_questions == 0:
        return 0
    return round(correct_answers / total_questions * 100)
```

**Answer comparison** (`_is_answer_correct`):

```python
def _is_answer_correct(
    user_answer: str,
    correct_answer: str,
    question_type: str,
) -> bool:
    ua = user_answer.strip().lower()
    ca = correct_answer.strip().lower()

    if question_type == "short_answer":
        # Allow containment — the user's answer need only contain the expected answer
        return ca in ua
    else:
        # Exact (case-insensitive) match for MCQ and true_false
        return ua == ca
```

| Scenario | Correct | Score |
|---|---|---|
| 5/5 correct | 5 | 100 |
| 3/6 correct | 3 | 50 |
| 0/5 correct | 0 | 0 |
| 0/0 (empty quiz) | 0 | 0 |
| 1/3 correct | 1 | 33 |

---

## Review Mode

When viewing a specific attempt via `GET /quizzes/{id}/attempts/{attempt_id}`, the response includes per-question grading details:

```json
{
  "id": "attempt-uuid",
  "quiz_id": "quiz-uuid",
  "score": 50,
  "total_questions": 2,
  "correct_answers": 1,
  "completed_at": "2026-07-10T08:00:00Z",
  "created_at": "2026-07-10T08:00:00Z",
  "results": [
    {
      "question_text": "What is the capital of France?",
      "user_answer": "London",
      "correct_answer": "Paris",
      "explanation": "Paris is the capital of France.",
      "is_correct": false
    },
    {
      "question_text": "Is the sky blue?",
      "user_answer": "True",
      "correct_answer": "True",
      "explanation": "The sky appears blue due to Rayleigh scattering.",
      "is_correct": true
    }
  ]
}
```

The `results` array is constructed by walking the stored `answers` JSON, looking up each `question_id` in the `QuizQuestion` table, comparing the user's answer to `correct_answer`, and attaching the `explanation` from the question.

---

## Cache Integration

Cache keys follow the `resource:user_id:suffix` pattern established in the flashcard system.

**Key format:**

```python
def quiz_list_key(user_id: UUID, document_id: UUID | None = None) -> str:
    ...

def quiz_detail_key(user_id: UUID, quiz_id: UUID) -> str:
    return f"quiz:{user_id}:{quiz_id}"

def quiz_attempt_list_key(user_id: UUID, quiz_id: UUID) -> str:
    ...
```

**TTL:** 120 seconds.

**Cache invalidation** (`invalidate_quiz_cache`):

| Event | Pattern | Action |
|---|---|---|
| Quiz generated | `quiz:{user_id}:*` | Full flush |
| Quiz deleted | `quiz:{user_id}:*` | Full flush |
| Document quizzes deleted | `quiz:{user_id}:*` | Full flush |
| Attempt submitted | `quiz:{user_id}:*` | Full flush |

Because quiz lists and detail keys share the `quiz:{user_id}` prefix, a single wildcard flush covers all cached quiz data for a user.

---

## Security

### Authentication

All quiz endpoints require the `get_current_active_user` dependency, which validates the JWT `access_token` from the `Authorization: Bearer <token>` header. Unauthenticated requests return 401.

### Ownership Enforcement

Every service function takes `user_id: UUID` as its first parameter and scopes all queries with `user_id == current_user.id`:

| Operation | Query pattern |
|---|---|
| Generate quiz | `Document.query.filter(Document.id == doc_id, Document.user_id == user_id)` |
| List quizzes | `Quiz.query.filter(Quiz.user_id == user_id)` |
| Get quiz | `Quiz.query.filter(Quiz.id == quiz_id, Quiz.user_id == user_id)` |
| Delete quiz | `Quiz.query.filter(Quiz.id == quiz_id, Quiz.user_id == user_id)` |
| Submit attempt | `Quiz.query.filter(Quiz.id == quiz_id, Quiz.user_id == user_id)` |
| List attempts | `Quiz.query.filter(Quiz.id == quiz_id, Quiz.user_id == user_id)` |

Cross-user access returns HTTP 404 (not 403) to avoid leaking whether a resource exists.

### Data Integrity

- **Soft delete**: Quizzes and attempts are soft-deleted (`deleted_at` is set), never hard-deleted. All queries filter `deleted_at.is_(None)`.
- **Cascading**: Deleting a quiz cascades to its questions. Deleting a document cascades to its quizzes. Deleting a user cascades to their quizzes and attempts.
- **Server-side scoring**: Scores are calculated on the server, not trusted from the client. The `score` and `correct_answers` fields are computed from the submitted answers against the stored `correct_answer` values.

---

## Configuration

All quiz settings are in `app/core/config.py`:

| Setting | Default | Description |
|---|---|---|
| `QUIZ_BATCH_SIZE` | 5 | Number of chunks per Gemini batch |
| `QUIZ_MAX_PER_BATCH` | 8 | Maximum questions produced per batch |
| `QUIZ_MODEL` | `models/gemini-2.0-flash-lite` | Gemini model for quiz generation |
| `QUIZ_TIMEOUT_SECONDS` | 60 | Per-batch Gemini timeout |
| `QUIZ_MAX_QUESTIONS` | 50 | Maximum total questions per quiz |
| `QUIZ_DEFAULT_QUESTION_COUNT` | 5 | Default question_count parameter |

Override via environment variables: `QUIZ_MODEL=models/gemini-2.5-pro-exp-03-25`

---

## Testing

**Test file:** `tests/test_quizzes.py` — 78 tests across 8 test classes.

| Class | Focus | Count |
|---|---|---|
| `TestParser` | `clean_gemini_response`, `parse_quiz_json` | 10 |
| `TestValidation` | `validate_question` — MCQ, TF, SA edge cases | 11 |
| `TestBatching` | `batch_chunks` — empty, single, multiple | 4 |
| `TestScoring` | `calculate_score` — perfect, partial, zero | 5 |
| `TestAnswerComparison` | `_is_answer_correct` — type-aware comparison | 8 |
| `TestGenerateService` | `generate_quiz` — doc not found, not processed, no chunks, Gemini failure | 6 |
| `TestAPI` | Full HTTP integration — generate, list, get, delete, cross-user | 13 |
| `TestAttempt` | Attempt lifecycle — submit, score, review, retry, cross-user | 11 |
| `TestPagination` | Quiz + attempt pagination | 2 |
| `TestSecurity` | Auth required, cross-user isolation | 4 |
| `TestCache` | Cache key format + invalidation | 2 |

**Runner:**
```bash
# Quiz-specific tests
cd backend && source venv/bin/activate
python -m pytest tests/test_quizzes.py -v --tb=short

# Full backend regression
python -m pytest tests/ -v --tb=short
```

---

## Future Improvements

- **Gemini model upgrade**: Switch from `google.generativeai` (deprecated) to `google.genai` when the migration is ready.
- **Quiz pooling**: Cache generated questions so repeated generation requests on the same document return existing questions.
- **Adaptive difficulty**: Track past attempt performance and bias question generation toward weaker areas.
- **Bulk generate**: Support generating quizzes for all documents at once with a single endpoint call.
- **Quiz export**: Export quizzes as JSON, CSV, or Anki-compatible format.
- **Question bank**: Allow users to manually create/edit/delete individual questions.
- **Time-limited attempts**: Add a `time_limit_seconds` field to quizzes and enforce it on attempt submission.
- **Question type expansion**: Add fill-in-the-blank, matching, and ordering question types.
- **AI-assisted review**: After grading, show a summary of common mistakes and suggest review topics.
- **Tagging and categorisation**: Tag questions by topic and filter quizzes by tag.
