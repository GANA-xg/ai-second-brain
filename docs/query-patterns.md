# Query Patterns

This document describes the most common database queries used by the AI Second Brain backend and the indexes that support them.

---

# 1. List User Documents

Purpose:
Display all documents uploaded by a user.

Query

```sql
SELECT *
FROM documents
WHERE user_id = ?
ORDER BY created_at DESC;
```

Index

```
ix_documents_user_created
(user_id, created_at)
```

---

# 2. List Ready Documents

Purpose:
Retrieve processed documents available for RAG.

Query

```sql
SELECT *
FROM documents
WHERE user_id = ?
AND status = 'READY';
```

Index

```
ix_documents_user_status
(user_id, status)
```

---

# 3. Retrieve Document Chunks

Purpose:
Load chunks for embedding retrieval.

Query

```sql
SELECT *
FROM chunks
WHERE document_id = ?
ORDER BY chunk_index;
```

Index

```
ix_chunks_document_order
(document_id, chunk_index)
```

---

# 4. Load Conversation History

Purpose:
Load all chat messages for a conversation.

Query

```sql
SELECT *
FROM messages
WHERE conversation_id = ?
ORDER BY created_at;
```

Index

```
ix_messages_conversation_created
(conversation_id, created_at)
```

---

# 5. Load User Flashcards

Purpose:
Retrieve flashcards created for a user.

Query

```sql
SELECT *
FROM flashcards
WHERE user_id = ?
ORDER BY created_at DESC;
```

Index

```
ix_flashcards_user_created
(user_id, created_at)
```

---

# 6. Retrieve User Memories

Purpose:
Retrieve stored long-term memories.

Query

```sql
SELECT *
FROM memories
WHERE user_id = ?
AND memory_type = ?;
```

Index

```
ix_memories_user_type
(user_id, memory_type)
```

---

# 7. Retrieve Quiz Attempts

Purpose:
Show quiz history.

Query

```sql
SELECT *
FROM quiz_attempts
WHERE quiz_id = ?
ORDER BY created_at DESC;
```

Index

```
ix_quiz_attempts_quiz_created
(quiz_id, created_at)
```

---

# Design Principles

- Every user-owned resource includes `user_id`.
- Frequently filtered columns are indexed.
- Frequently sorted queries use composite indexes.
- Constraints enforce valid data.
- UUIDs are used as primary keys.
- UTC timestamps are used throughout the schema.