from enum import Enum

from pydantic import BaseModel


class EntityType(str, Enum):
    AGENT = "agent"
    MCP_SERVER = "mcp_server"


class TargetEnvironment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class QuotaProfile(str, Enum):
    SMALL = "small"
    STANDARD = "standard"
    LARGE = "large"


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str
    deployment_id: str | None = None
