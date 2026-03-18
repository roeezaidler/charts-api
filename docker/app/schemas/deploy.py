import re

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import DeploymentType, EntityType, TargetEnvironment


def expand_dot_keys(d: dict) -> dict:
    """Expand dot-notation keys into nested dicts. e.g. {'service.port': 80} -> {'service': {'port': 80}}"""
    result = {}
    for key, value in d.items():
        if isinstance(value, dict):
            value = expand_dot_keys(value)
        parts = key.split(".")
        target = result
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        # Merge if target already has a dict at this key
        if parts[-1] in target and isinstance(target[parts[-1]], dict) and isinstance(value, dict):
            target[parts[-1]].update(value)
        else:
            target[parts[-1]] = value
    return result


def normalize_entity_name(name: str) -> str:
    """Lowercase, replace invalid chars with dashes, strip leading/trailing dashes."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)  # replace anything not alphanumeric/dash
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
    deployment_type: DeploymentType = Field(default=DeploymentType.DEPLOY, description="'deploy' for new, 'upgrade' for existing")
    values_override: dict | None = Field(
        default=None,
        description="Optional Helm values to override chart defaults",
    )

    @field_validator("values_override")
    @classmethod
    def expand_values(cls, v: dict | None) -> dict | None:
        if v is not None:
            return expand_dot_keys(v)
        return v


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
