import asyncio

import httpx
import structlog

from app.backends.base import AppStatus, DeploymentBackend, DeploymentResult, DeletionResult
from app.config import Settings
from app.core.exceptions import ArgocdError

logger = structlog.get_logger()


class ArgoCDBackend(DeploymentBackend):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.argocd_server_url,
            headers={"Authorization": f"Bearer {settings.argocd_auth_token}"},
            verify=False,  # internal cluster communication
            timeout=60.0,
        )

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
    ) -> DeploymentResult:
        """Create or update an ArgoCD Application that deploys a Helm chart."""
        application = {
            "metadata": {
                "name": app_name,
                "namespace": "argocd",
                "labels": labels,
                "finalizers": ["resources-finalizer.argocd.argoproj.io"],
            },
            "spec": {
                "project": argocd_project,
                "source": {
                    "repoURL": chart_repo_url,
                    "chart": chart_name,
                    "targetRevision": chart_version,
                    "helm": {
                        "values": values_yaml,
                    },
                },
                "destination": {
                    "server": "https://kubernetes.default.svc",
                    "namespace": namespace,
                },
                "syncPolicy": {
                    "automated": {
                        "prune": True,
                        "selfHeal": True,
                    },
                    "syncOptions": ["CreateNamespace=true"],
                },
            },
        }

        try:
            # Try to create the Application
            resp = await self.client.post("/api/v1/applications", json=application)

            if resp.status_code == 409:
                # Application already exists - update it
                resp = await self.client.put(
                    f"/api/v1/applications/{app_name}",
                    json=application,
                )

            if resp.status_code not in (200, 201):
                error_msg = resp.text
                logger.error("argocd_deploy_failed", app=app_name, status=resp.status_code, error=error_msg)
                return DeploymentResult(
                    success=False,
                    app_name=app_name,
                    namespace=namespace,
                    error_message=f"ArgoCD API error ({resp.status_code}): {error_msg}",
                )

            logger.info("argocd_application_created", app=app_name, namespace=namespace)

            # Wait for sync to complete
            await self._wait_for_sync(app_name)

            return DeploymentResult(success=True, app_name=app_name, namespace=namespace)

        except httpx.HTTPError as e:
            error_msg = f"ArgoCD connection error: {e}"
            logger.error("argocd_connection_error", app=app_name, error=str(e))
            return DeploymentResult(
                success=False, app_name=app_name, namespace=namespace, error_message=error_msg
            )

    async def _wait_for_sync(self, app_name: str) -> None:
        """Poll ArgoCD until the Application is synced and healthy, or timeout."""
        timeout = self.settings.argocd_sync_timeout
        poll_interval = 5
        elapsed = 0

        while elapsed < timeout:
            try:
                status = await self.get_status(app_name)
                if status.sync_status == "Synced" and status.health_status == "Healthy":
                    logger.info("argocd_sync_complete", app=app_name)
                    return
                if status.health_status == "Degraded":
                    raise ArgocdError(f"Application {app_name} is degraded")
            except ArgocdError:
                raise
            except Exception:
                pass  # transient errors during polling

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning("argocd_sync_timeout", app=app_name, timeout=timeout)

    async def delete(self, app_name: str) -> DeletionResult:
        """Delete an ArgoCD Application (cascades to delete K8s resources via finalizer)."""
        try:
            resp = await self.client.delete(
                f"/api/v1/applications/{app_name}",
                params={"cascade": "true"},
            )
            if resp.status_code == 404:
                return DeletionResult(success=True)  # already gone
            if resp.status_code not in (200, 204):
                return DeletionResult(success=False, error_message=f"ArgoCD delete failed: {resp.text}")

            logger.info("argocd_application_deleted", app=app_name)
            return DeletionResult(success=True)

        except httpx.HTTPError as e:
            return DeletionResult(success=False, error_message=str(e))

    async def get_status(self, app_name: str) -> AppStatus:
        """Get sync and health status of an ArgoCD Application."""
        try:
            resp = await self.client.get(f"/api/v1/applications/{app_name}")
            if resp.status_code == 404:
                return AppStatus(sync_status="Unknown", health_status="Missing")
            if resp.status_code != 200:
                raise ArgocdError(f"Failed to get app status: {resp.text}", resp.status_code)

            data = resp.json()
            status = data.get("status", {})
            sync = status.get("sync", {}).get("status", "Unknown")
            health = status.get("health", {}).get("status", "Unknown")
            created = data.get("metadata", {}).get("creationTimestamp")

            return AppStatus(sync_status=sync, health_status=health, created_at=created)

        except httpx.HTTPError as e:
            raise ArgocdError(f"ArgoCD connection error: {e}")

    async def list_apps(self, label_selector: str) -> list[dict]:
        """List ArgoCD Applications matching a label selector."""
        try:
            resp = await self.client.get(
                "/api/v1/applications",
                params={"selector": label_selector},
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            apps = []
            for item in data.get("items", []):
                metadata = item.get("metadata", {})
                status = item.get("status", {})
                spec = item.get("spec", {})
                apps.append({
                    "name": metadata.get("name"),
                    "namespace": spec.get("destination", {}).get("namespace"),
                    "labels": metadata.get("labels", {}),
                    "sync_status": status.get("sync", {}).get("status", "Unknown"),
                    "health_status": status.get("health", {}).get("status", "Unknown"),
                    "created_at": metadata.get("creationTimestamp"),
                })
            return apps

        except httpx.HTTPError:
            return []

    async def close(self):
        await self.client.aclose()
