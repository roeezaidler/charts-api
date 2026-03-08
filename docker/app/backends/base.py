from dataclasses import dataclass


@dataclass
class DeploymentResult:
    success: bool
    release_name: str
    namespace: str
    error_message: str | None = None


@dataclass
class DeletionResult:
    success: bool
    error_message: str | None = None


@dataclass
class ReleaseStatus:
    status: str  # deployed, failed, pending, uninstalling, etc.
    namespace: str
    chart: str | None = None
    app_version: str | None = None
