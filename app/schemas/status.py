from pydantic import BaseModel


class DeploymentStatusResponse(BaseModel):
    deployment_id: str
    entity_name: str
    entity_type: str
    namespace: str
    sync_status: str
    health_status: str
    connection_url: str | None = None
    public_connection_url: str | None = None
    created_at: str | None = None
    expires_at: str | None = None


class DeploymentListResponse(BaseModel):
    deployments: list[DeploymentStatusResponse]
    total: int


class DeleteResponse(BaseModel):
    status: str
    message: str
