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
    argocd_server_url: str = "https://users-argocd.devops.nsogroup.com"
    argocd_auth_token: str = ""
    argocd_project: str = "default"
    argocd_namespace: str = "user-charts"  # namespace where ArgoCD + charts-api live
    argocd_sync_timeout: int = 300  # seconds to wait for sync

    # Internal TLS - path to CA bundle for verifying internal HTTPS (Artifactory, ArgoCD, etc.)
    # Set to "" to skip verification (not recommended for production)
    ca_bundle_path: str = "/etc/ssl/certs/internal-ca.crt"

    # Artifactory Helm repo URL as registered in ArgoCD
    # This is what goes into the ArgoCD Application source.repoURL
    artifactory_helm_repo_url: str = "https://artifactory.nsogroup.com/artifactory/devops-helm-release-local"

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
