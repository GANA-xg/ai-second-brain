from fastapi import APIRouter

from app.api.v1.endpoints import health, auth, files, chat, memory, flashcards, quiz, voice


api_router = APIRouter()


api_router.include_router(
    health.router,
    prefix="/health",
    tags=["Health"],
)

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"],
)

api_router.include_router(
    files.router,
    prefix="/files",
    tags=["Files"],
)

api_router.include_router(
    chat.router,
    tags=["Chat"],
)

api_router.include_router(
    memory.router,
    prefix="/memories",
    tags=["Memories"],
)

api_router.include_router(
    flashcards.router,
    tags=["Flashcards"],
)

api_router.include_router(
    quiz.router,
    tags=["Quizzes"],
)

api_router.include_router(
    voice.router,
    tags=["Voice"],
)
