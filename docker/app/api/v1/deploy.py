from fastapi import APIRouter, Depends, HTTPException
import structlog

from app.schemas.deploy import DeployRequest, DeployResponse, DeleteRequest, DeleteResponse
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
        logger.error("deploy_error", deployment_id=e.deployment_id, error=e.message)
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "deployment_id": e.deployment_id, "message": e.message},
        )
    except Exception as e:
        logger.exception("deploy_unhandled_error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "message": str(e)},
        )


@router.post(
    "/api/infra/delete",
    response_model=DeleteResponse,
    responses={500: {"model": ErrorResponse}},
)
async def delete(
    request: DeleteRequest,
    service: DeploymentService = Depends(get_deployment_service),
):
    logger.info(
        "delete_request",
        entity_name=request.entity_name,
        entity_type=request.entity_type,
        owner=request.owner_username,
        env=request.target_environment,
    )
    try:
        await service.delete_deployment(
            entity_name=request.entity_name,
            entity_type=request.entity_type.value,
            owner_username=request.owner_username,
            target_environment=request.target_environment.value,
        )
        return DeleteResponse(status="success", message="Deployment deleted")
    except DeploymentError as e:
        logger.error("delete_error", deployment_id=e.deployment_id, error=e.message)
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "deployment_id": e.deployment_id, "message": e.message},
        )
    except Exception as e:
        logger.exception("delete_unhandled_error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "message": str(e)},
        )
