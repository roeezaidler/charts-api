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

    def _get_service_urls(self, service_name: str, namespace: str) -> tuple[str, str | None]:
        """Query K8s API for a Service and return (internal_url, external_url).

        For LoadBalancer services, retries a few times waiting for the external IP.
        """
        internal_url = f"http://{service_name}.{namespace}.svc.cluster.local"
        external_url = None

        try:
            for attempt in range(6):  # up to ~15s waiting for LB IP
                svc = self.core_v1.read_namespaced_service(name=service_name, namespace=namespace)

                if svc.spec.type == "LoadBalancer" and svc.status.load_balancer.ingress:
                    ingress = svc.status.load_balancer.ingress[0]
                    host = ingress.ip or ingress.hostname
                    port = svc.spec.ports[0].port
                    external_url = f"http://{host}:{port}"
                    break
                elif svc.spec.type == "LoadBalancer" and attempt < 5:
                    logger.debug("waiting_for_lb_ip", service=service_name, attempt=attempt)
                    time.sleep(3)
                else:
                    break

            if svc.spec.type == "NodePort" and not external_url:
                node_port = svc.spec.ports[0].node_port
                nodes = self.core_v1.list_node()
                for node in nodes.items:
                    for addr in node.status.addresses:
                        if addr.type == "ExternalIP":
                            external_url = f"http://{addr.address}:{node_port}"
                            break
                    if external_url:
                        break

        except ApiException as e:
            logger.warning("service_query_failed", service=service_name, namespace=namespace, error=str(e))

        return internal_url, external_url

    async def get_service_urls(self, service_name: str, namespace: str) -> tuple[str, str | None]:
        """Async wrapper around the synchronous K8s client."""
        return await asyncio.to_thread(self._get_service_urls, service_name, namespace)

    def _list_services_in_namespace(self, namespace: str) -> list[str]:
        try:
            services = self.core_v1.list_namespaced_service(namespace=namespace)
            return [svc.metadata.name for svc in services.items]
        except ApiException:
            return []

    async def list_services_in_namespace(self, namespace: str) -> list[str]:
        return await asyncio.to_thread(self._list_services_in_namespace, namespace)
