import uuid
from datetime import datetime, timedelta, timezone

import structlog

from app.backends.base import DeploymentBackend
from app.config import Settings
from app.core.exceptions import DeploymentError
from app.core.namespace import build_namespace, build_release_name
from app.core.quota_profiles import build_values_overrides, values_to_yaml
from app.schemas.deploy import DeployRequest, DeployResponse
from app.schemas.status import DeploymentStatusResponse
from app.services.kubernetes_service import KubernetesService

logger = structlog.get_logger()

# Label keys used on ArgoCD Applications for tracking
LABEL_MANAGED_BY = "charts-api/managed-by"
LABEL_OWNER = "charts-api/owner"
LABEL_ENTITY_TYPE = "charts-api/entity-type"
LABEL_ENVIRONMENT = "charts-api/environment"
LABEL_ENTITY_NAME = "charts-api/entity-name"
LABEL_EXPIRES_AT = "charts-api/expires-at"


class DeploymentService:
    def __init__(self, backend: DeploymentBackend, k8s_service: KubernetesService, settings: Settings):
        self.backend = backend
        self.k8s = k8s_service
        self.settings = settings

    async def create_deployment(self, request: DeployRequest) -> DeployResponse:
        deployment_id = str(uuid.uuid4())
        namespace = build_namespace(request.entity_type.value, request.owner_username, request.target_environment.value)
        app_name = build_release_name(request.entity_name, request.target_environment.value)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=request.ttl_days)

        # Build labels for tracking on the ArgoCD Application
        labels = {
            LABEL_MANAGED_BY: "charts-api",
            LABEL_OWNER: request.owner_username,
            LABEL_ENTITY_TYPE: request.entity_type.value,
            LABEL_ENVIRONMENT: request.target_environment.value,
            LABEL_ENTITY_NAME: request.entity_name,
            LABEL_EXPIRES_AT: expires_at.isoformat(),
        }

        # Build Helm values overrides
        values = build_values_overrides(
            entity_name=request.entity_name,
            entity_type=request.entity_type.value,
            artifactory_path=request.artifactory_path,
            quota_profile=request.quota_profile.value,
            target_environment=request.target_environment.value,
            owner_username=request.owner_username,
            groups=request.groups,
            service_type=self.settings.default_service_type,
            service_port=self.settings.default_service_port,
        )
        values_yaml = values_to_yaml(values)

        logger.info(
            "deploying",
            deployment_id=deployment_id,
            app_name=app_name,
            namespace=namespace,
            chart=f"{request.chart_name}:{request.chart_version}",
        )

        # Deploy via backend (ArgoCD or Helm)
        result = await self.backend.deploy(
            app_name=app_name,
            chart_repo_url=self.settings.artifactory_helm_repo_url,
            chart_name=request.chart_name,
            chart_version=request.chart_version,
            namespace=namespace,
            values_yaml=values_yaml,
            labels=labels,
            argocd_project=self.settings.argocd_project,
        )

        if not result.success:
            raise DeploymentError(deployment_id, result.error_message or "Unknown error")

        # Discover service URLs
        # The service name depends on the Helm chart - typically it's the entity_name or the release name.
        # We try entity_name first (as shown in the example chart: service name is "mcp-server"),
        # then fall back to the release name.
        service_name = request.entity_name
        internal_url, external_url = await self.k8s.get_service_urls(service_name, namespace)

        logger.info(
            "deploy_success",
            deployment_id=deployment_id,
            app_name=app_name,
            internal_url=internal_url,
            external_url=external_url,
        )

        return DeployResponse(
            status="success",
            deployment_id=deployment_id,
            namespace=namespace,
            connection_url=internal_url,
            public_connection_url=external_url,
            message="Deployment triggered successfully",
        )

    async def get_deployment_status(self, app_name: str) -> DeploymentStatusResponse:
        status = await self.backend.get_status(app_name)

        # Get labels from ArgoCD to reconstruct metadata
        apps = await self.backend.list_apps(f"{LABEL_MANAGED_BY}=charts-api")
        app_data = next((a for a in apps if a["name"] == app_name), None)

        entity_name = ""
        entity_type = ""
        namespace = ""
        expires_at = None
        if app_data:
            labels = app_data.get("labels", {})
            entity_name = labels.get(LABEL_ENTITY_NAME, "")
            entity_type = labels.get(LABEL_ENTITY_TYPE, "")
            namespace = app_data.get("namespace", "")
            expires_at = labels.get(LABEL_EXPIRES_AT)

        internal_url = None
        external_url = None
        if namespace and entity_name:
            internal_url, external_url = await self.k8s.get_service_urls(entity_name, namespace)

        return DeploymentStatusResponse(
            deployment_id=app_name,
            entity_name=entity_name,
            entity_type=entity_type,
            namespace=namespace,
            sync_status=status.sync_status,
            health_status=status.health_status,
            connection_url=internal_url,
            public_connection_url=external_url,
            created_at=status.created_at,
            expires_at=expires_at,
        )

    async def list_deployments(
        self,
        owner: str | None = None,
        environment: str | None = None,
    ) -> list[DeploymentStatusResponse]:
        # Build label selector
        selectors = [f"{LABEL_MANAGED_BY}=charts-api"]
        if owner:
            selectors.append(f"{LABEL_OWNER}={owner}")
        if environment:
            selectors.append(f"{LABEL_ENVIRONMENT}={environment}")
        label_selector = ",".join(selectors)

        apps = await self.backend.list_apps(label_selector)

        results = []
        for app_data in apps:
            labels = app_data.get("labels", {})
            entity_name = labels.get(LABEL_ENTITY_NAME, "")
            namespace = app_data.get("namespace", "")

            internal_url = None
            external_url = None
            if namespace and entity_name:
                internal_url, external_url = await self.k8s.get_service_urls(entity_name, namespace)

            results.append(
                DeploymentStatusResponse(
                    deployment_id=app_data["name"],
                    entity_name=entity_name,
                    entity_type=labels.get(LABEL_ENTITY_TYPE, ""),
                    namespace=namespace,
                    sync_status=app_data.get("sync_status", "Unknown"),
                    health_status=app_data.get("health_status", "Unknown"),
                    connection_url=internal_url,
                    public_connection_url=external_url,
                    created_at=app_data.get("created_at"),
                    expires_at=labels.get(LABEL_EXPIRES_AT),
                )
            )
        return results

    async def delete_deployment(self, app_name: str) -> None:
        result = await self.backend.delete(app_name)
        if not result.success:
            raise DeploymentError(app_name, result.error_message or "Failed to delete")
        logger.info("deployment_deleted", app_name=app_name)
