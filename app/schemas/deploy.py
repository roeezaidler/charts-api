from pydantic import BaseModel, Field

from app.schemas.common import EntityType, QuotaProfile, TargetEnvironment


class DeployRequest(BaseModel):
    entity_name: str = Field(
        ...,
        min_length=1,
        max_length=253,
        pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$",
        description="DNS-compatible name for the entity",
    )
    entity_type: EntityType
    chart_name: str = Field(..., min_length=1)
    chart_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+.*$")
    artifactory_path: str = Field(..., description="Docker image path in Artifactory")
    owner_username: str = Field(..., min_length=1, max_length=63)
    groups: list[str] = Field(default_factory=list)
    target_environment: TargetEnvironment
    ttl_days: int = Field(default=7, ge=1, le=365)
    quota_profile: QuotaProfile = QuotaProfile.STANDARD


class DeployResponse(BaseModel):
    status: str
    deployment_id: str
    namespace: str
    connection_url: str
    public_connection_url: str | None = None
    message: str
