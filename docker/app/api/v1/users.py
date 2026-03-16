from fastapi import APIRouter, Depends, HTTPException
import structlog

from app.services.rancher_service import RancherService
from app.dependencies import get_rancher_service

logger = structlog.get_logger()
router = APIRouter()


@router.get("/api/infra/user/{username}/project")
async def get_user_project(
    username: str,
    rancher: RancherService = Depends(get_rancher_service),
):
    try:
        return await rancher.get_user_project(username)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("get_user_project_error", username=username)
        raise HTTPException(status_code=500, detail=str(e))
