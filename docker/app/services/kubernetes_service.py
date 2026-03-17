import asyncio
import time

from kubernetes import client, config
from kubernetes.client.rest import ApiException
import structlog

from app.config import Settings

logger = structlog.get_logger()


class KubernetesService:
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.k8s_in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config(config_file=settings.k8s_kubeconfig or None)
        self.core_v1 = client.CoreV1Api()
        self.networking_v1 = client.NetworkingV1Api()

    def _ensure_namespace(self, namespace: str, project_id: str | None = None) -> None:
        """Create namespace if it doesn't exist, with Rancher project label."""
        try:
            self.core_v1.read_namespace(name=namespace)
            logger.info("namespace_exists", namespace=namespace)
            return
        except ApiException as e:
            if e.status != 404:
                raise

        # Build namespace with project annotation
        labels = {}
        annotations = {}
        if project_id and self.settings.rancher_cluster_id:
            full_project_id = f"{self.settings.rancher_cluster_id}:{project_id}"
            annotations["field.cattle.io/projectId"] = full_project_id

        ns = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=namespace,
                labels=labels,
                annotations=annotations,
            )
        )
        self.core_v1.create_namespace(body=ns)
        logger.info("namespace_created", namespace=namespace, project_id=project_id)

    async def ensure_namespace(self, namespace: str, project_id: str | None = None) -> None:
        """Async wrapper for namespace creation."""
        await asyncio.to_thread(self._ensure_namespace, namespace, project_id)

    def _get_service_urls(self, namespace: str) -> tuple[str, str | None]:
        """Find the internal service URL and the ingress URL for a deployment.

        Returns (internal_url, ingress_url).
        """
        internal_url = None
        ingress_url = None

        try:
            # Find internal service URL
            services = self.core_v1.list_namespaced_service(namespace=namespace)
            for svc in services.items:
                svc_name = svc.metadata.name
                port = svc.spec.ports[0].port if svc.spec.ports else 80
                internal_url = f"http://{svc_name}.{namespace}.svc.cluster.local:{port}"
                break

            # Find ingress URL
            ingresses = self.networking_v1.list_namespaced_ingress(namespace=namespace)
            for ing in ingresses.items:
                if ing.spec.rules:
                    rule = ing.spec.rules[0]
                    host = rule.host
                    if rule.http and rule.http.paths:
                        # Strip regex suffix from path, e.g. /test2-dev(/|$)(.*) -> /test2-dev
                        raw_path = rule.http.paths[0].path or "/"
                        clean_path = raw_path.split("(")[0].rstrip("/")
                        protocol = "https" if ing.spec.tls else "http"
                        ingress_url = f"{protocol}://{host}{clean_path}"
                    else:
                        protocol = "https" if ing.spec.tls else "http"
                        ingress_url = f"{protocol}://{host}"
                    break

        except ApiException as e:
            logger.warning("service_query_failed", namespace=namespace, error=str(e))

        return internal_url or f"http://{namespace}.svc.cluster.local", ingress_url

    async def get_service_urls(self, namespace: str) -> tuple[str, str | None]:
        """Async wrapper around the synchronous K8s client."""
        return await asyncio.to_thread(self._get_service_urls, namespace)

    def _list_services_in_namespace(self, namespace: str) -> list[str]:
        try:
            services = self.core_v1.list_namespaced_service(namespace=namespace)
            return [svc.metadata.name for svc in services.items]
        except ApiException:
            return []

    async def list_services_in_namespace(self, namespace: str) -> list[str]:
        return await asyncio.to_thread(self._list_services_in_namespace, namespace)
