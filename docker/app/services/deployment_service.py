import uuid
from datetime import datetime, timedelta, timezone

import structlog

from app.backends.helm_backend import HelmBackend
from app.config import Settings
from app.core.exceptions import DeploymentError
from app.core.namespace import build_namespace, build_release_name
from app.core.quota_profiles import build_values_overrides, values_to_yaml, deep_merge
from app.schemas.deploy import DeployRequest, DeployResponse
from app.schemas.status import DeploymentStatusResponse
from app.services.kubernetes_service import KubernetesService

logger = structlog.get_logger()


class DeploymentService:
    def __init__(self, helm: HelmBackend, k8s_service: KubernetesService, settings: Settings):
        self.helm = helm
        self.k8s = k8s_service
        self.settings = settings

    async def create_deployment(self, request: DeployRequest) -> DeployResponse:
        deployment_id = str(uuid.uuid4())
        namespace = build_namespace(request.entity_type.value, request.owner_username, request.target_environment.value)
        release_name = build_release_name(request.entity_name, request.target_environment.value)

        # Build Helm values from quota profile
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

        # Merge user-provided values_override on top
        if request.values_override:
            values = deep_merge(values, request.values_override)

        values_yaml = values_to_yaml(values)

        chart_ref = f"{self.settings.artifactory_helm_repo_name}/{request.chart_name}"

        logger.info(
            "deploying",
            deployment_id=deployment_id,
            release=release_name,
            namespace=namespace,
            chart=f"{request.chart_name}:{request.chart_version}",
            impersonate_user=request.owner_username,
        )

        # Ensure Artifactory Helm repo is configured
        await self.helm.ensure_repo()

        # Deploy via Helm with Rancher impersonation
        result = await self.helm.deploy(
            release_name=release_name,
            chart_ref=chart_ref,
            chart_version=request.chart_version,
            namespace=namespace,
            values_yaml=values_yaml,
            impersonate_user=request.owner_username,
            impersonate_groups=request.groups or None,
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

    async def delete_release(self, release_name: str, namespace: str, impersonate_user: str | None = None, impersonate_groups: list[str] | None = None) -> None:
        result = await self.helm.delete(release_name, namespace, impersonate_user, impersonate_groups)
        if not result.success:
            raise DeploymentError(release_name, result.error_message or "Failed to delete")
        logger.info("release_deleted", release=release_name, namespace=namespace)
