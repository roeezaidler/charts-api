from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class DeploymentResult:
    success: bool
    app_name: str
    namespace: str
    error_message: str | None = None


@dataclass
class DeletionResult:
    success: bool
    error_message: str | None = None


@dataclass
class AppStatus:
    sync_status: str  # Synced, OutOfSync, Unknown
    health_status: str  # Healthy, Progressing, Degraded, Missing, Unknown
    created_at: str | None = None


class DeploymentBackend(ABC):
    """Abstract interface for deployment backends (ArgoCD or direct Helm)."""

    @abstractmethod
    async def deploy(
        self,
        app_name: str,
        chart_repo_url: str,
        chart_name: str,
        chart_version: str,
        namespace: str,
        values_yaml: str,
        labels: dict[str, str],
        argocd_project: str = "default",
    ) -> DeploymentResult: ...

    @abstractmethod
    async def delete(self, app_name: str) -> DeletionResult: ...

    @abstractmethod
    async def get_status(self, app_name: str) -> AppStatus: ...

    @abstractmethod
    async def list_apps(self, label_selector: str) -> list[dict]: ...
