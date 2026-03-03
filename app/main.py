from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.config import Settings
from app.backends.argocd_backend import ArgoCDBackend
from app.backends.helm_backend import HelmBackend
from app.services.deployment_service import DeploymentService
from app.services.kubernetes_service import KubernetesService
from app.scheduler.ttl_scheduler import start_scheduler, stop_scheduler
from app.api.v1.router import api_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    # Initialize backend
    if settings.deployment_backend == "argocd":
        backend = ArgoCDBackend(settings)
        logger.info("backend_initialized", type="argocd", server=settings.argocd_server_url)
    else:
        backend = HelmBackend(settings)
        logger.info("backend_initialized", type="helm")

    # Initialize K8s service
    k8s_service = KubernetesService(settings)

    # Wire up the deployment service
    app.state.deployment_service = DeploymentService(backend, k8s_service, settings)

    # Start TTL cleanup scheduler
    scheduler = start_scheduler(settings, backend)
    logger.info("app_started")

    yield

    # Shutdown
    stop_scheduler(scheduler)
    if hasattr(backend, "close"):
        await backend.close()
    logger.info("app_stopped")


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(
        title="Charts API - Helm Deployment Server",
        description="API for deploying MCP servers and agents to Kubernetes via ArgoCD",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(api_router)
    return app


app = create_app()
