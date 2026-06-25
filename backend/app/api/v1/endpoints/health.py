from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services.health_service import get_health

router = APIRouter()


@router.get(
    "/",
    response_model=HealthResponse
)
def health():

    return get_health()
@router.get("/ready")
def ready():

    return {
        "status": "ready",

        "postgres": "pending",

        "redis": "pending",

        "qdrant": "pending"
    }