from functools import lru_cache

from fastapi import Request

from app.config import Settings
from app.backends.argocd_backend import ArgoCDBackend
from app.backends.helm_backend import HelmBackend
from app.services.deployment_service import DeploymentService
from app.services.kubernetes_service import KubernetesService


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_deployment_service(request: Request) -> DeploymentService:
    return request.app.state.deployment_service
