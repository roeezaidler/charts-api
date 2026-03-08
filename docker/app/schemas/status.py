from pydantic import BaseModel


class DeploymentStatusResponse(BaseModel):
    release_name: str
    namespace: str
    status: str  # deployed, failed, pending-install, pending-upgrade, uninstalling, etc.
    chart: str | None = None
    app_version: str | None = None
    connection_url: str | None = None
    public_connection_url: str | None = None


class ReleaseListResponse(BaseModel):
    releases: list[dict]
    total: int


class DeleteResponse(BaseModel):
    status: str
    message: str
