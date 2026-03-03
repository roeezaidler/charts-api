from fastapi import APIRouter, Depends, HTTPException, Query
import structlog

from app.schemas.status import DeploymentStatusResponse, DeploymentListResponse, DeleteResponse
from app.schemas.common import ErrorResponse
from app.core.exceptions import DeploymentError
from app.services.deployment_service import DeploymentService
from app.dependencies import get_deployment_service

logger = structlog.get_logger()
router = APIRouter()


@router.get(
    "/api/infra/deploy/{app_name}",
    response_model=DeploymentStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_deployment(
    app_name: str,
    service: DeploymentService = Depends(get_deployment_service),
):
    try:
        return await service.get_deployment_status(app_name)
    except Exception as e:
        logger.exception("get_status_error", app_name=app_name)
        raise HTTPException(status_code=404, detail={"status": "error", "message": str(e)})


@router.get(
    "/api/infra/deployments",
    response_model=DeploymentListResponse,
)
async def list_deployments(
    owner: str | None = Query(None),
    environment: str | None = Query(None),
    service: DeploymentService = Depends(get_deployment_service),
):
    deployments = await service.list_deployments(owner=owner, environment=environment)
    return DeploymentListResponse(deployments=deployments, total=len(deployments))


@router.delete(
    "/api/infra/deploy/{app_name}",
    response_model=DeleteResponse,
    responses={500: {"model": ErrorResponse}},
)
async def delete_deployment(
    app_name: str,
    service: DeploymentService = Depends(get_deployment_service),
):
    try:
        await service.delete_deployment(app_name)
        return DeleteResponse(status="success", message=f"Deployment {app_name} deleted")
    except DeploymentError as e:
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "message": e.message},
        )
