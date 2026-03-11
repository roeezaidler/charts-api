from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.config import Settings
from app.backends.helm_backend import HelmBackend
from app.services.deployment_service import DeploymentService
from app.services.kubernetes_service import KubernetesService
from app.services.rancher_service import RancherService
from app.api.v1.router import api_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    helm = HelmBackend(settings)
    k8s_service = KubernetesService(settings)
    rancher = RancherService(settings)

    app.state.deployment_service = DeploymentService(helm, k8s_service, rancher, settings)
    logger.info("app_started")

    yield

    await rancher.close()
    logger.info("app_stopped")


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(
        title="Charts API - Helm Deployment Server",
        description="API for deploying Helm charts to Kubernetes via Rancher with user impersonation",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(api_router)
    return app


app = create_app()
