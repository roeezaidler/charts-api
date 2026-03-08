from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="healthy")


@router.get("/readiness", response_model=HealthResponse)
async def readiness():
    return HealthResponse(status="ready")
