from fastapi import APIRouter, Depends, HTTPException, Query
import structlog

from app.schemas.status import DeploymentStatusResponse, ReleaseListResponse, DeleteResponse
from app.schemas.common import ErrorResponse
from app.core.exceptions import DeploymentError
from app.services.deployment_service import DeploymentService
from app.dependencies import get_deployment_service

logger = structlog.get_logger()
router = APIRouter()


@router.get(
    "/api/infra/deploy/{release_name}",
    response_model=DeploymentStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_deployment(
    release_name: str,
    namespace: str = Query(..., description="Kubernetes namespace of the release"),
    service: DeploymentService = Depends(get_deployment_service),
):
    try:
        return await service.get_release_status(release_name, namespace)
    except DeploymentError:
        raise HTTPException(status_code=404, detail={"status": "error", "message": f"Release {release_name} not found"})
    except Exception as e:
        logger.exception("get_status_error", release=release_name)
        raise HTTPException(status_code=500, detail={"status": "error", "message": str(e)})


@router.get(
    "/api/infra/deployments",
    response_model=ReleaseListResponse,
)
async def list_deployments(
    namespace: str | None = Query(None, description="Filter by namespace"),
    service: DeploymentService = Depends(get_deployment_service),
):
    releases = await service.list_releases(namespace=namespace)
    return ReleaseListResponse(releases=releases, total=len(releases))


@router.delete(
    "/api/infra/deploy/{release_name}",
    response_model=DeleteResponse,
    responses={500: {"model": ErrorResponse}},
)
async def delete_deployment(
    release_name: str,
    namespace: str = Query(..., description="Kubernetes namespace of the release"),
    owner_username: str | None = Query(None, description="Rancher username to impersonate for RBAC"),
    service: DeploymentService = Depends(get_deployment_service),
):
    try:
        await service.delete_release(release_name, namespace, owner_username)
        return DeleteResponse(status="success", message=f"Release {release_name} deleted")
    except DeploymentError as e:
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "message": e.message},
        )
