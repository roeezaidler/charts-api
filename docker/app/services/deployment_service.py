import asyncio
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
from app.services.litellm_service import LiteLLMService
from app.services.rancher_service import RancherService

logger = structlog.get_logger()


class DeploymentService:
    def __init__(self, helm: HelmBackend, k8s_service: KubernetesService, rancher: RancherService, litellm: LiteLLMService, settings: Settings):
        self.helm = helm
        self.k8s = k8s_service
        self.rancher = rancher
        self.litellm = litellm
        self.settings = settings

    async def create_deployment(self, request: DeployRequest) -> DeployResponse:
        deployment_id = str(uuid.uuid4())

        # Resolve username to Rancher user ID + AD groups + project ID
        user_id, groups, project_id = await self.rancher.resolve_user(request.owner_username)
        logger.info("resolved_impersonation", username=request.owner_username, user_id=user_id, groups=groups, project_id=project_id)

        # Extract group name from project_id (e.g. "p-qa" -> "qa")
        group_name = project_id.split("-", 1)[1] if project_id else "default"
        namespace = build_namespace(group_name, request.entity_type.value, request.entity_name, request.target_environment.value)
        release_name = build_release_name(group_name, request.entity_name, request.target_environment.value)

        # For "deploy" type, check that the namespace doesn't already exist
        if request.deployment_type.value == "deploy":
            if await self.rancher.namespace_exists(namespace):
                raise DeploymentError(
                    deployment_id,
                    f"Deployment already exists (namespace '{namespace}'). Use deployment_type='upgrade' to update it.",
                )

        # Force networkPool to the user's project group (always overrides user input)
        values = request.values_override or {}
        subchart = "ai-agent-core" if request.entity_type.value == "agent" else "mcp-server-core"
        if request.chart_name == subchart:
            # Deploying the subchart directly
            values.setdefault("service", {})["networkPool"] = group_name
        else:
            # Subchart is embedded — prefix with subchart name
            values.setdefault(subchart, {}).setdefault("service", {})["networkPool"] = group_name

        # Generate LiteLLM API key for agent deployments (before helm deploy so we can inject it)
        litellm_api_key = None
        if request.entity_type.value == "agent" and self.litellm.master_key:
            try:
                key_data = await self.litellm.generate_key(group_name, request.entity_name)
                litellm_api_key = key_data["key"]
                logger.info("litellm_key_created", key_alias=key_data["key_alias"], deployment_id=deployment_id)
                # Inject the key as a chart value
                values.setdefault("ai-agent-core", {}).setdefault("env", {})["LITELLM_API_KEY"] = litellm_api_key
            except Exception as e:
                logger.warning("litellm_key_failed", error=str(e), deployment_id=deployment_id)

        # Build values YAML from override (or empty)
        values_yaml = yaml.dump(values, default_flow_style=False)

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

        # Discover service URLs (service name matches the Helm release name)
        internal_url, external_url = await self.k8s.get_service_urls(namespace)

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
            litellm_api_key=litellm_api_key,
            message="Deployment successful",
        )

    async def get_release_status(self, release_name: str, namespace: str) -> DeploymentStatusResponse:
        status = await self.helm.get_status(release_name, namespace)
        if status is None:
            raise DeploymentError(release_name, f"Release {release_name} not found in namespace {namespace}")

        internal_url, external_url = await self.k8s.get_service_urls(namespace)

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
        if namespace:
            return await self.helm.list_releases(namespace)

        # List across all our managed namespaces
        namespaces = await self.rancher.list_managed_namespaces()
        results = await asyncio.gather(
            *[self.helm.list_releases(ns) for ns in namespaces]
        )
        releases = []
        for r in results:
            releases.extend(r)
        return releases

    async def delete_deployment(
        self,
        entity_name: str,
        entity_type: str,
        owner_username: str,
        target_environment: str,
    ) -> None:
        """Delete a deployment by resolving the user, namespace, and release name."""
        user_id, groups, project_id = await self.rancher.resolve_user(owner_username)

        group_name = project_id.split("-", 1)[1] if project_id else "default"
        namespace = build_namespace(group_name, entity_type, entity_name, target_environment)
        release_name = build_release_name(group_name, entity_name, target_environment)

        logger.info("deleting_deployment", release=release_name, namespace=namespace, user_id=user_id)

        result = await self.helm.delete(release_name, namespace, user_id, groups or None)
        if not result.success:
            raise DeploymentError(release_name, result.error_message or "Failed to delete")
        logger.info("release_deleted", release=release_name, namespace=namespace)

        # Delete the namespace after the release is uninstalled
        await self.rancher.delete_namespace(namespace)

