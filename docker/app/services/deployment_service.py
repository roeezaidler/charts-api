import uuid

import structlog
import yaml

from app.backends.helm_backend import HelmBackend
from app.config import Settings
from app.core.exceptions import DeploymentError
from app.core.namespace import build_namespace, build_release_name
from app.schemas.deploy import DeployRequest, DeployResponse
from app.schemas.status import DeploymentStatusResponse
from app.services.kubernetes_service import KubernetesService
from app.services.rancher_service import RancherService

logger = structlog.get_logger()


class DeploymentService:
    def __init__(self, helm: HelmBackend, k8s_service: KubernetesService, rancher: RancherService, settings: Settings):
        self.helm = helm
        self.k8s = k8s_service
        self.rancher = rancher
        self.settings = settings

    async def create_deployment(self, request: DeployRequest) -> DeployResponse:
        deployment_id = str(uuid.uuid4())
        namespace = build_namespace(request.entity_type.value, request.owner_username, request.target_environment.value)
        release_name = build_release_name(request.entity_name, request.target_environment.value)

        # Resolve username to Rancher user ID + AD groups + project ID
        user_id, groups, project_id = await self.rancher.resolve_user(request.owner_username)
        logger.info("resolved_impersonation", username=request.owner_username, user_id=user_id, groups=groups, project_id=project_id)

        # Build values YAML from override (or empty)
        values_yaml = yaml.dump(request.values_override or {}, default_flow_style=False)

        chart_ref = f"{self.settings.artifactory_helm_repo_name}/{request.chart_name}"

        logger.info(
            "deploying",
            deployment_id=deployment_id,
            release=release_name,
            namespace=namespace,
            chart=f"{request.chart_name}:{request.chart_version}",
            impersonate_user=user_id,
            project_id=project_id,
        )

        # Create namespace via Rancher API as admin (with project label)
        await self.rancher.ensure_namespace(namespace, project_id)

        # Ensure Artifactory Helm repo is configured
        await self.helm.ensure_repo()

        # Deploy via Helm with Rancher impersonation (user ID + AD groups)
        result = await self.helm.deploy(
            release_name=release_name,
            chart_ref=chart_ref,
            chart_version=request.chart_version,
            namespace=namespace,
            values_yaml=values_yaml,
            impersonate_user=user_id,
            impersonate_groups=groups or None,
        )

        if not result.success:
            raise DeploymentError(deployment_id, result.error_message or "Unknown error")

        # Discover service URLs
        service_name = request.entity_name
        internal_url, external_url = await self.k8s.get_service_urls(service_name, namespace)

        logger.info(
            "deploy_success",
            deployment_id=deployment_id,
            release=release_name,
            internal_url=internal_url,
            external_url=external_url,
        )

        return DeployResponse(
            status="success",
            deployment_id=deployment_id,
            namespace=namespace,
            connection_url=internal_url,
            public_connection_url=external_url,
            message="Deployment successful",
        )

    async def get_release_status(self, release_name: str, namespace: str) -> DeploymentStatusResponse:
        status = await self.helm.get_status(release_name, namespace)
        if status is None:
            raise DeploymentError(release_name, f"Release {release_name} not found in namespace {namespace}")

        internal_url, external_url = await self.k8s.get_service_urls(release_name, namespace)

        return DeploymentStatusResponse(
            release_name=release_name,
            namespace=namespace,
            status=status.status,
            chart=status.chart,
            app_version=status.app_version,
            connection_url=internal_url,
            public_connection_url=external_url,
        )

    async def list_releases(self, namespace: str | None = None) -> list[dict]:
        return await self.helm.list_releases(namespace)

    async def delete_release(self, release_name: str, namespace: str, owner_username: str | None = None) -> None:
        impersonate_user = None
        impersonate_groups = None
        if owner_username:
            impersonate_user, impersonate_groups, _ = await self.rancher.resolve_user(owner_username)

        result = await self.helm.delete(release_name, namespace, impersonate_user, impersonate_groups)
        if not result.success:
            raise DeploymentError(release_name, result.error_message or "Failed to delete")
        logger.info("release_deleted", release=release_name, namespace=namespace)
