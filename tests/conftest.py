from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.backends.base import AppStatus, DeploymentResult, DeletionResult
from app.config import Settings
from app.main import create_app
from app.services.deployment_service import DeploymentService
from app.services.kubernetes_service import KubernetesService


class MockBackend:
    """Mock backend that returns success without calling ArgoCD or Helm."""

    async def deploy(self, **kwargs) -> DeploymentResult:
        return DeploymentResult(
            success=True,
            app_name=kwargs.get("app_name", "test-app"),
            namespace=kwargs.get("namespace", "test-ns"),
        )

    async def delete(self, app_name: str) -> DeletionResult:
        return DeletionResult(success=True)

    async def get_status(self, app_name: str) -> AppStatus:
        return AppStatus(sync_status="Synced", health_status="Healthy", created_at="2024-01-01T00:00:00Z")

    async def list_apps(self, label_selector: str) -> list[dict]:
        return [
            {
                "name": "test-entity-dev",
                "namespace": "agent-testuser-dev",
                "labels": {
                    "charts-api/managed-by": "charts-api",
                    "charts-api/owner": "testuser",
                    "charts-api/entity-type": "agent",
                    "charts-api/environment": "dev",
                    "charts-api/entity-name": "test-entity",
                    "charts-api/expires-at": "2099-01-01T00:00:00+00:00",
                },
                "sync_status": "Synced",
                "health_status": "Healthy",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]


class MockKubernetesService:
    async def get_service_urls(self, service_name: str, namespace: str) -> tuple[str, str | None]:
        return (f"http://{service_name}.{namespace}.svc.cluster.local", None)

    async def list_services_in_namespace(self, namespace: str) -> list[str]:
        return ["test-service"]


@pytest.fixture
def settings():
    return Settings(
        deployment_backend="argocd",
        argocd_server_url="https://argocd.test",
        argocd_auth_token="test-token",
        artifactory_helm_repo_url="https://artifactory.test/api/helm/repo",
        k8s_in_cluster=False,
    )


@pytest.fixture
def mock_backend():
    return MockBackend()


@pytest.fixture
def mock_k8s():
    return MockKubernetesService()


@pytest.fixture
def deployment_service(mock_backend, mock_k8s, settings):
    return DeploymentService(mock_backend, mock_k8s, settings)


@pytest.fixture
def client(settings, mock_backend, mock_k8s):
    app = create_app()
    app.state.settings = settings
    app.state.deployment_service = DeploymentService(mock_backend, mock_k8s, settings)
    return TestClient(app)
