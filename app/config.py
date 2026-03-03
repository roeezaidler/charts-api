from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Deployment backend
    deployment_backend: Literal["argocd", "helm"] = "argocd"

    # ArgoCD
    argocd_server_url: str = "https://argocd.internal"
    argocd_auth_token: str = ""
    argocd_project: str = "default"
    argocd_sync_timeout: int = 300  # seconds to wait for sync

    # Artifactory (Helm chart source registered in ArgoCD)
    artifactory_helm_repo_url: str = ""

    # Kubernetes
    k8s_in_cluster: bool = True
    k8s_kubeconfig: str = ""

    # Helm (fallback backend)
    helm_binary: str = "helm"
    helm_timeout: int = 300

    # Defaults
    default_service_type: str = "ClusterIP"
    default_service_port: int = 8080

    # TTL cleanup
    ttl_check_interval_minutes: int = 60

    model_config = {"env_file": ".env", "env_prefix": "CHARTS_API_"}
