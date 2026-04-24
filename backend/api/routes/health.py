"""Health check endpoint."""

from fastapi import APIRouter
from models.schemas import HealthResponse
from config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    services = {
        "database": "healthy",
        "llm_provider": "configured",
        "image_provider": "configured",
        "tts_provider": "configured",
        "storage": "configured",
    }

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        services=services,
    )
