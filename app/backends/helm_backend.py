import asyncio
import json
import tempfile
from pathlib import Path

import yaml
import structlog

from app.backends.base import AppStatus, DeploymentBackend, DeploymentResult, DeletionResult
from app.config import Settings

logger = structlog.get_logger()


class HelmBackend(DeploymentBackend):
    """Fallback backend that runs helm upgrade --install directly."""

    def __init__(self, settings: Settings):
        self.helm_bin = settings.helm_binary
        self.timeout = settings.helm_timeout

    async def _run_helm(self, args: list[str]) -> tuple[int, str, str]:
        cmd = [self.helm_bin] + args
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
        return process.returncode, stdout.decode(), stderr.decode()

    async def deploy(
        self,
        app_name: str,
        chart_repo_url: str,
        chart_name: str,
        chart_version: str,
        namespace: str,
        values_yaml: str,
        labels: dict[str, str],
        argocd_project: str = "default",
    ) -> DeploymentResult:
        values_file = Path(tempfile.mktemp(suffix=".yaml"))
        try:
            values_file.write_text(values_yaml)

            args = [
                "upgrade", "--install",
                app_name,
                chart_name,
                "--version", chart_version,
                "--namespace", namespace,
                "--create-namespace",
                "--values", str(values_file),
                "--timeout", f"{self.timeout}s",
                "--wait",
            ]

            returncode, stdout, stderr = await self._run_helm(args)

            if returncode != 0:
                return DeploymentResult(
                    success=False,
                    app_name=app_name,
                    namespace=namespace,
                    error_message=f"Helm deploy failed: {stderr}",
                )

            return DeploymentResult(success=True, app_name=app_name, namespace=namespace)
        finally:
            values_file.unlink(missing_ok=True)

    async def delete(self, app_name: str) -> DeletionResult:
        # We need namespace but helm can find it from the release
        args = ["uninstall", app_name, "--wait"]
        returncode, stdout, stderr = await self._run_helm(args)
        if returncode != 0:
            return DeletionResult(success=False, error_message=stderr)
        return DeletionResult(success=True)

    async def get_status(self, app_name: str) -> AppStatus:
        args = ["status", app_name, "--output", "json"]
        returncode, stdout, stderr = await self._run_helm(args)
        if returncode != 0:
            return AppStatus(sync_status="Unknown", health_status="Unknown")
        data = json.loads(stdout)
        helm_status = data.get("info", {}).get("status", "unknown")
        health = "Healthy" if helm_status == "deployed" else "Degraded"
        return AppStatus(sync_status="Synced" if helm_status == "deployed" else "Unknown", health_status=health)

    async def list_apps(self, label_selector: str) -> list[dict]:
        args = ["list", "--all-namespaces", "--output", "json"]
        returncode, stdout, stderr = await self._run_helm(args)
        if returncode != 0:
            return []
        releases = json.loads(stdout)
        return [
            {
                "name": r.get("name"),
                "namespace": r.get("namespace"),
                "labels": {},
                "sync_status": "Synced" if r.get("status") == "deployed" else "Unknown",
                "health_status": "Healthy" if r.get("status") == "deployed" else "Unknown",
                "created_at": None,
            }
            for r in releases
        ]
