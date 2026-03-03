from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    backend: str


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)):
    return HealthResponse(status="healthy", backend=settings.deployment_backend)


@router.get("/readiness", response_model=HealthResponse)
async def readiness(settings: Settings = Depends(get_settings)):
    return HealthResponse(status="ready", backend=settings.deployment_backend)
