from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import structlog

from app.backends.base import DeploymentBackend
from app.config import Settings

logger = structlog.get_logger()

LABEL_MANAGED_BY = "charts-api/managed-by"
LABEL_EXPIRES_AT = "charts-api/expires-at"

# Store backend reference for the cleanup job
_backend: DeploymentBackend | None = None


async def cleanup_expired_deployments():
    """Scan ArgoCD Applications managed by charts-api and delete expired ones."""
    if _backend is None:
        return

    logger.info("ttl_cleanup_started")
    now = datetime.now(timezone.utc)

    try:
        apps = await _backend.list_apps(f"{LABEL_MANAGED_BY}=charts-api")
        expired_count = 0

        for app_data in apps:
            labels = app_data.get("labels", {})
            expires_at_str = labels.get(LABEL_EXPIRES_AT)
            if not expires_at_str:
                continue

            try:
                expires_at = datetime.fromisoformat(expires_at_str)
            except ValueError:
                logger.warning("invalid_expires_at", app=app_data["name"], value=expires_at_str)
                continue

            if expires_at <= now:
                app_name = app_data["name"]
                logger.info("ttl_expiring_deployment", app=app_name, expired_at=expires_at_str)

                result = await _backend.delete(app_name)
                if result.success:
                    expired_count += 1
                    logger.info("ttl_deployment_deleted", app=app_name)
                else:
                    logger.error("ttl_deletion_failed", app=app_name, error=result.error_message)

        logger.info("ttl_cleanup_finished", expired=expired_count, total_checked=len(apps))

    except Exception:
        logger.exception("ttl_cleanup_error")


def start_scheduler(settings: Settings, backend: DeploymentBackend) -> AsyncIOScheduler:
    global _backend
    _backend = backend

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        cleanup_expired_deployments,
        trigger=IntervalTrigger(minutes=settings.ttl_check_interval_minutes),
        id="ttl_cleanup",
        name="TTL Deployment Cleanup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler_started", interval_minutes=settings.ttl_check_interval_minutes)
    return scheduler


def stop_scheduler(scheduler: AsyncIOScheduler):
    scheduler.shutdown(wait=False)
    logger.info("scheduler_stopped")
