from app.core.config import settings
from app.services.vector_service import get_vector_service


def get_health() -> dict:
    """Check health of all dependencies: PostgreSQL, Redis, Qdrant."""
    health = {
        "status": "ok",
        "dependencies": {},
    }

    # Check PostgreSQL
    try:
        from app.db.session import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health["dependencies"]["postgresql"] = {"status": "healthy"}
    except Exception as exc:
        health["dependencies"]["postgresql"] = {
            "status": "unhealthy",
            "error": str(exc)[:200],
        }
        health["status"] = "degraded"

    # Check Redis
    try:
        import redis

        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        health["dependencies"]["redis"] = {"status": "healthy"}
    except Exception as exc:
        health["dependencies"]["redis"] = {"status": "unhealthy", "error": str(exc)[:200]}
        health["status"] = "degraded"

    # Check Qdrant
    try:
        vector_service = get_vector_service()
        qdrant_health = vector_service.health_check()
        health["dependencies"]["qdrant"] = qdrant_health
        if qdrant_health["status"] != "healthy":
            health["status"] = "degraded"
    except Exception as exc:
        health["dependencies"]["qdrant"] = {"status": "unhealthy", "error": str(exc)[:200]}
        health["status"] = "degraded"

    return health