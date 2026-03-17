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
        """Find services in the namespace and return (internal_url, external_url).

        Searches all services in the namespace rather than guessing the service name.
        For LoadBalancer services, retries a few times waiting for the external IP.
        """
        internal_url = None
        external_url = None

        try:
            for attempt in range(6):  # up to ~15s waiting for LB IP
                services = self.core_v1.list_namespaced_service(namespace=namespace)
                for svc in services.items:
                    svc_name = svc.metadata.name
                    internal_url = f"http://{svc_name}.{namespace}.svc.cluster.local"

                    if svc.spec.type == "LoadBalancer" and svc.status.load_balancer.ingress:
                        ingress = svc.status.load_balancer.ingress[0]
                        host = ingress.ip or ingress.hostname
                        port = svc.spec.ports[0].port
                        external_url = f"http://{host}:{port}"
                        return internal_url, external_url

                    if svc.spec.type == "NodePort":
                        node_port = svc.spec.ports[0].node_port
                        nodes = self.core_v1.list_node()
                        for node in nodes.items:
                            for addr in node.status.addresses:
                                if addr.type == "ExternalIP":
                                    external_url = f"http://{addr.address}:{node_port}"
                                    return internal_url, external_url

                # If we found a LB service but no IP yet, wait and retry
                lb_pending = any(s.spec.type == "LoadBalancer" for s in services.items)
                if lb_pending and attempt < 5:
                    logger.debug("waiting_for_lb_ip", namespace=namespace, attempt=attempt)
                    time.sleep(3)
                else:
                    break

        except ApiException as e:
            logger.warning("service_query_failed", namespace=namespace, error=str(e))

        return internal_url or f"http://{namespace}.svc.cluster.local", external_url

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
