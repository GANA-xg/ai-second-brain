# Database Design

## Entities
- User
- Document
- Chunk
- Conversation
- Message
- Flashcard
- Quiz
- QuizAttempt
- Memory

## Relationships

User
├── Documents
│   └── Chunks
├── Conversations
│   └── Messages
├── Flashcards
├── Quizzes
│   └── QuizAttempts
└── Memory

## Document Lifecycle

UPLOADING
→ UPLOADED
→ PROCESSING
→ READY

Alternative states:
- FAILED
- DELETED

## Common Fields

- id
- created_at
- updated_at
- deleted_at

## Common Query Patterns

- Documents by user
- Chunks by document
- Conversations by user
- Messages by conversation
- Flashcards by user
- Quizzes by user
- Memory by user