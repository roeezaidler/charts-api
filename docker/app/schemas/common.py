from enum import Enum

from pydantic import BaseModel


class EntityType(str, Enum):
    AGENT = "agent"
    MCP_SERVER = "mcp_server"


class TargetEnvironment(str, Enum):
    DEV = "dev"
    RELEASE = "release"


class DeploymentType(str, Enum):
    DEPLOY = "deploy"
    UPGRADE = "upgrade"


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str
    deployment_id: str | None = None
