from pydantic import BaseModel, Field

from app.schemas.common import EntityType, TargetEnvironment


class DeployRequest(BaseModel):
    entity_name: str = Field(
        ...,
        min_length=1,
        max_length=253,
        pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$",
        description="DNS-compatible name for the entity",
    )
    entity_type: EntityType
    chart_name: str = Field(..., min_length=1, description="Helm chart name in Artifactory")
    chart_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+.*$")
    artifactory_path: str = Field(..., description="Docker image path in Artifactory")
    owner_username: str = Field(..., min_length=1, max_length=63, description="Rancher username to impersonate")
    target_environment: TargetEnvironment
    values_override: dict | None = Field(
        default=None,
        description="Optional Helm values to override chart defaults",
    )


class DeployResponse(BaseModel):
    status: str
    deployment_id: str
    namespace: str
    connection_url: str
    public_connection_url: str | None = None
    message: str
