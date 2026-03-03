from fastapi import APIRouter

from app.api.v1 import deploy, status, health

api_router = APIRouter()
api_router.include_router(deploy.router, tags=["deploy"])
api_router.include_router(status.router, tags=["status"])
api_router.include_router(health.router, tags=["health"])
