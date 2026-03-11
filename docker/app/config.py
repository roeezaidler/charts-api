from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Rancher - used to proxy K8s API with user impersonation
    rancher_url: str = ""  # e.g. https://rancher.nsogroup.com
    rancher_cluster_id: str = ""  # e.g. c-m-xxxxx
    rancher_token: str = ""  # Admin token with impersonation rights

    # Internal TLS - path to CA bundle for verifying internal HTTPS
    ca_bundle_path: str = "/etc/ssl/certs/internal-ca.crt"

    # Artifactory Helm repo - added to helm via `helm repo add`
    artifactory_helm_repo_url: str = "https://artifactory.nsogroup.com/artifactory/devops-helm-release-local"
    artifactory_helm_repo_name: str = "artifactory"
    artifactory_username: str = ""
    artifactory_password: str = ""

    # Helm
    helm_binary: str = "helm"
    helm_timeout: int = 300

    # LDAP - for resolving user AD group memberships
    ldap_server: str = ""  # e.g. ldap://dc01.nsogroup.com
    ldap_username: str = ""  # e.g. svc_charts_api (will be prefixed with nsogroup\\)
    ldap_password: str = ""
    ldap_base_dn: str = "OU=NSOGROUP,DC=NSOGROUP,DC=COM"

    # Kubernetes (for service URL discovery)
    k8s_in_cluster: bool = True
    k8s_kubeconfig: str = ""

    model_config = {"env_file": ".env", "env_prefix": "CHARTS_API_"}

    @property
    def rancher_k8s_api_url(self) -> str:
        """Rancher K8s API proxy URL for the managed cluster."""
        return f"{self.rancher_url}/k8s/clusters/{self.rancher_cluster_id}"
