import asyncio
import json
import tempfile
from pathlib import Path

import structlog

from app.backends.base import DeploymentResult, DeletionResult, ReleaseStatus
from app.config import Settings

logger = structlog.get_logger()


class HelmBackend:
    """Helm backend that deploys via Rancher K8s API proxy with user impersonation."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.helm_bin = settings.helm_binary
        self.timeout = settings.helm_timeout

    def _base_args(self, impersonate_user: str | None = None, impersonate_groups: list[str] | None = None) -> list[str]:
        """Build common Helm args for Rancher API proxy + impersonation."""
        args = []
        if self.settings.rancher_url and self.settings.rancher_cluster_id:
            args.extend(["--kube-apiserver", self.settings.rancher_k8s_api_url])
            args.extend(["--kube-token", self.settings.rancher_token])
        if self.settings.ca_bundle_path:
            args.extend(["--kube-ca-file", self.settings.ca_bundle_path])
        if impersonate_user:
            args.extend(["--kube-as-user", impersonate_user])
        for group in (impersonate_groups or []):
            args.extend(["--kube-as-group", group])
        return args

    async def _run_helm(self, args: list[str]) -> tuple[int, str, str]:
        cmd = [self.helm_bin] + args
        # Log the command (redact token)
        safe_cmd = [a if a != self.settings.rancher_token else "***" for a in cmd]
        logger.debug("helm_exec", cmd=" ".join(safe_cmd))

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
        return process.returncode, stdout.decode(), stderr.decode()

    async def ensure_repo(self) -> None:
        """Add the Artifactory Helm repo if not already added."""
        args = [
            "repo", "add",
            self.settings.artifactory_helm_repo_name,
            self.settings.artifactory_helm_repo_url,
            "--force-update",
        ]
        if self.settings.artifactory_username:
            args.extend(["--username", self.settings.artifactory_username])
        if self.settings.artifactory_password:
            args.extend(["--password", self.settings.artifactory_password])
        if self.settings.ca_bundle_path:
            args.extend(["--ca-file", self.settings.ca_bundle_path])

        returncode, stdout, stderr = await self._run_helm(args)
        if returncode != 0:
            logger.error("helm_repo_add_failed", error=stderr)
            raise RuntimeError(f"Failed to add Helm repo: {stderr}")

        await self._run_helm(["repo", "update"])
        logger.info("helm_repo_configured", repo=self.settings.artifactory_helm_repo_name)

    async def deploy(
        self,
        release_name: str,
        chart_ref: str,
        chart_version: str,
        namespace: str,
        values_yaml: str,
        impersonate_user: str,
        impersonate_groups: list[str] | None = None,
    ) -> DeploymentResult:
        """Deploy a Helm chart via Rancher with user impersonation."""
        values_file = Path(tempfile.mktemp(suffix=".yaml"))
        try:
            values_file.write_text(values_yaml)

            args = self._base_args(impersonate_user, impersonate_groups)
            args.extend([
                "upgrade", "--install",
                release_name,
                chart_ref,
                "--version", chart_version,
                "--namespace", namespace,
                "--create-namespace",
                "--values", str(values_file),
                "--timeout", f"{self.timeout}s",
                "--wait",
            ])

            returncode, stdout, stderr = await self._run_helm(args)

            if returncode != 0:
                logger.error("helm_deploy_failed", release=release_name, error=stderr)
                return DeploymentResult(
                    success=False,
                    release_name=release_name,
                    namespace=namespace,
                    error_message=f"Helm deploy failed: {stderr}",
                )

            logger.info("helm_deploy_success", release=release_name, namespace=namespace)
            return DeploymentResult(success=True, release_name=release_name, namespace=namespace)
        finally:
            values_file.unlink(missing_ok=True)

    async def delete(
        self,
        release_name: str,
        namespace: str,
        impersonate_user: str | None = None,
        impersonate_groups: list[str] | None = None,
    ) -> DeletionResult:
        """Uninstall a Helm release."""
        args = self._base_args(impersonate_user, impersonate_groups)
        args.extend(["uninstall", release_name, "--namespace", namespace, "--wait"])

        returncode, stdout, stderr = await self._run_helm(args)
        if returncode != 0:
            return DeletionResult(success=False, error_message=stderr)
        return DeletionResult(success=True)

    async def get_status(self, release_name: str, namespace: str) -> ReleaseStatus | None:
        """Get status of a Helm release."""
        args = self._base_args()
        args.extend(["status", release_name, "--namespace", namespace, "--output", "json"])

        returncode, stdout, stderr = await self._run_helm(args)
        if returncode != 0:
            return None
        data = json.loads(stdout)
        return ReleaseStatus(
            status=data.get("info", {}).get("status", "unknown"),
            namespace=namespace,
            chart=data.get("chart", {}).get("metadata", {}).get("name"),
            app_version=data.get("chart", {}).get("metadata", {}).get("appVersion"),
        )

    async def list_releases(self, namespace: str | None = None) -> list[dict]:
        """List Helm releases. Uses the service account (no impersonation) for TTL cleanup."""
        args = self._base_args()
        if namespace:
            args.extend(["list", "--namespace", namespace, "--output", "json"])
        else:
            args.extend(["list", "--all-namespaces", "--output", "json"])

        returncode, stdout, stderr = await self._run_helm(args)
        if returncode != 0:
            return []
        return json.loads(stdout) if stdout.strip() else []
