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

    API_V1_PREFIX: str

    SECRET_KEY: str

    DATABASE_URL: str

    REDIS_URL: str

    QDRANT_URL: str

    GEMINI_API_KEY: str = ""


settings = Settings()