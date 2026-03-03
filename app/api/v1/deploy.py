from fastapi import APIRouter, Depends, HTTPException
import structlog

from app.schemas.deploy import DeployRequest, DeployResponse
from app.schemas.common import ErrorResponse
from app.core.exceptions import DeploymentError
from app.services.deployment_service import DeploymentService
from app.dependencies import get_deployment_service

logger = structlog.get_logger()
router = APIRouter()


@router.post(
    "/api/infra/deploy",
    response_model=DeployResponse,
    responses={500: {"model": ErrorResponse}},
)
async def deploy(
    request: DeployRequest,
    service: DeploymentService = Depends(get_deployment_service),
):
    logger.info(
        "deploy_request",
        entity_name=request.entity_name,
        entity_type=request.entity_type,
        owner=request.owner_username,
        env=request.target_environment,
    )
    try:
        return await service.create_deployment(request)
    except DeploymentError as e:
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "deployment_id": e.deployment_id, "message": e.message},
        )
    except Exception as e:
        logger.exception("deploy_unhandled_error")
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "message": str(e)},
        )
