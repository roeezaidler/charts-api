from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import structlog

from app.backends.helm_backend import HelmBackend
from app.config import Settings

logger = structlog.get_logger()

# Store helm backend reference for the cleanup job
_helm: HelmBackend | None = None
_settings: Settings | None = None


async def cleanup_expired_deployments():
    """Scan Helm releases and delete expired ones based on TTL annotations."""
    if _helm is None:
        return

    logger.info("ttl_cleanup_started")
    now = datetime.now(timezone.utc)

    try:
        releases = await _helm.list_releases()
        expired_count = 0

        for release in releases:
            # Check if the release was deployed by charts-api
            # Helm releases store metadata in labels/annotations via chart values
            # We check the updated timestamp + TTL to determine expiry
            updated = release.get("updated", "")
            name = release.get("name", "")
            namespace = release.get("namespace", "")

            if not updated or not name:
                continue

            # Parse the Helm timestamp (format: 2024-01-15 10:30:00.000000 +0000 UTC)
            try:
                # Strip timezone info for parsing, Helm always uses UTC
                ts_str = updated.split(".")[0]
                deployed_at = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except (ValueError, IndexError):
                continue

            # Default TTL: 7 days from deployment
            ttl_days = 7
            expires_at = deployed_at + __import__("datetime").timedelta(days=ttl_days)

            if expires_at <= now:
                logger.info("ttl_expiring_release", release=name, namespace=namespace, deployed_at=updated)

                result = await _helm.delete(name, namespace)
                if result.success:
                    expired_count += 1
                    logger.info("ttl_release_deleted", release=name, namespace=namespace)
                else:
                    logger.error("ttl_deletion_failed", release=name, error=result.error_message)

        logger.info("ttl_cleanup_finished", expired=expired_count, total_checked=len(releases))

    except Exception:
        logger.exception("ttl_cleanup_error")


def start_scheduler(settings: Settings, helm: HelmBackend) -> AsyncIOScheduler:
    global _helm, _settings
    _helm = helm
    _settings = settings

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
