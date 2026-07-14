from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str
    ENV: str

    DEBUG: bool

    BCRYPT_ROUNDS: int = 12
    
    API_V1_PREFIX: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    DATABASE_URL: str

    REDIS_URL: str

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "chunk_embeddings"
    VECTOR_DIMENSION: int = 384
    VECTOR_DISTANCE: str = "Cosine"
    QDRANT_TIMEOUT_SECONDS: int = 30
    QDRANT_MAX_RETRIES: int = 3

    GEMINI_API_KEY: str = ""

    # -- LLM provider (openrouter | openai | gemini) --
    LLM_PROVIDER: str = "openrouter"
    LLM_MODEL: str = "google/gemini-2.0-flash-lite"
    OPENROUTER_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    XAI_API_KEY: str = ""
    XAI_MODEL: str = "grok-2"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # -- RAG / Gemini settings --
    TOP_K: int = 10
    SCORE_THRESHOLD: float = 0.0
    MAX_CONTEXT_TOKENS: int = 4096
    MAX_RESPONSE_TOKENS: int = 1024
    PROMPT_VERSION: str = "v1"
    GEMINI_MODEL: str = "models/gemini-2.0-flash-lite"

    # -- Rate limiting --
    LOGIN_RATE_LIMIT: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 60

    REGISTER_RATE_LIMIT: int = 3
    REGISTER_RATE_LIMIT_WINDOW_SECONDS: int = 60

    # -- Password reset --
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 1
    APP_BASE_URL: str = "http://localhost:3000"

    REFRESH_RATE_LIMIT: int = 20
    REFRESH_RATE_LIMIT_WINDOW_SECONDS: int = 60

    LOGOUT_RATE_LIMIT: int = 30
    LOGOUT_RATE_LIMIT_WINDOW_SECONDS: int = 60

    # -- Auth logging --
    AUTH_LOG_LEVEL: str = "INFO"

    # -- File upload --
    UPLOAD_ROOT: str = "storage"
    MAX_UPLOAD_SIZE_MB: int = 50

    # -- Document processing pipeline --
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    PDF_MAX_PAGES: int = 100
    PROCESSING_TIMEOUT_SECONDS: int = 60

    # -- Embedding pipeline --
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_VERSION: str = "v1"
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_TIMEOUT_SECONDS: int = 30
    EMBEDDING_MAX_RETRIES: int = 3

    # -- Chat system --
    MAX_HISTORY_MESSAGES: int = 6
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100
    STREAM_TIMEOUT: int = 60
    AUTO_TITLE_LENGTH: int = 95
    CHAT_TIMEOUT_SECONDS: int = 60

    # -- Memory system --
    MEMORY_MIN_CONFIDENCE: float = 0.85
    MAX_PROMPT_MEMORIES: int = 5
    ENABLE_AUTO_MEMORY: bool = True
    MEMORY_EXTRACTION_MODEL: str = "models/gemini-2.0-flash-lite"
    MEMORY_EXTRACTION_TIMEOUT: int = 15

    # -- Flashcard system --
    FLASHCARD_BATCH_SIZE: int = 5
    FLASHCARD_MAX_PER_BATCH: int = 8
    FLASHCARD_MODEL: str = "models/gemini-2.0-flash-lite"
    FLASHCARD_TIMEOUT_SECONDS: int = 60

    # -- Quiz system --
    QUIZ_BATCH_SIZE: int = 5
    QUIZ_MAX_PER_BATCH: int = 8
    QUIZ_MODEL: str = "models/gemini-2.0-flash-lite"
    QUIZ_TIMEOUT_SECONDS: int = 60
    QUIZ_MAX_QUESTIONS: int = 50
    QUIZ_DEFAULT_QUESTION_COUNT: int = 5

    # -- Cache settings --
    CACHE_ENABLED: bool = True
    CACHE_DEFAULT_TTL: int = 60  # 1 minute
    CACHE_SEARCH_TTL: int = 300  # 5 minutes
    CACHE_DOCUMENT_TTL: int = 120  # 2 minutes
    CACHE_MEMORY_TTL: int = 600  # 10 minutes
    CACHE_CONVERSATION_TTL: int = 120  # 2 minutes
    CACHE_MESSAGE_TTL: int = 120  # 2 minutes

    GROK_API_KEY: str = ""
    LLM_PROVIDER: str = "grok"
settings = Settings()