from functools import lru_cache

from fastapi import Request

from app.config import Settings
from app.services.deployment_service import DeploymentService
from app.services.rancher_service import RancherService


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_deployment_service(request: Request) -> DeploymentService:
    return request.app.state.deployment_service


def get_rancher_service(request: Request) -> RancherService:
    return request.app.state.deployment_service.rancher
