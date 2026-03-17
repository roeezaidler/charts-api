import re

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import EntityType, TargetEnvironment


def normalize_entity_name(name: str) -> str:
    """Lowercase, replace spaces/underscores with dashes, strip leading/trailing dashes."""
    name = name.lower().replace(" ", "-").replace("_", "-")
    name = re.sub(r"-+", "-", name)  # collapse multiple dashes
    return name.strip("-")


class DeployRequest(BaseModel):
    entity_name: str = Field(
        ...,
        min_length=1,
        max_length=253,
        description="DNS-compatible name for the entity",
    )

    @field_validator("entity_name")
    @classmethod
    def clean_entity_name(cls, v: str) -> str:
        return normalize_entity_name(v)
    entity_type: EntityType
    chart_name: str = Field(..., min_length=1, description="Helm chart name in Artifactory")
    chart_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+.*$")
    owner_username: str = Field(..., min_length=1, max_length=63, description="Rancher username to impersonate")
    target_environment: TargetEnvironment
    values_override: dict | None = Field(
        default=None,
        description="Optional Helm values to override chart defaults",
    )


class DeleteRequest(BaseModel):
    entity_name: str = Field(..., min_length=1, max_length=253, description="Name of the deployed entity")

    @field_validator("entity_name")
    @classmethod
    def clean_entity_name(cls, v: str) -> str:
        return normalize_entity_name(v)
    entity_type: EntityType
    owner_username: str = Field(..., min_length=1, max_length=63, description="Owner username used during deploy")
    target_environment: TargetEnvironment


class DeleteResponse(BaseModel):
    status: str
    message: str


class DeployResponse(BaseModel):
    status: str
    deployment_id: str
    namespace: str
    connection_url: str
    public_connection_url: str | None = None
    message: str
