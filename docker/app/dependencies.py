from functools import lru_cache

from fastapi import Request

from app.config import Settings
from app.services.deployment_service import DeploymentService


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_deployment_service(request: Request) -> DeploymentService:
    return request.app.state.deployment_service
