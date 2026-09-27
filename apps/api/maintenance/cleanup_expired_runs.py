"""Idempotent maintenance command to expire or clean up anonymous runs exceeding retention hours and purge expired rate limit buckets."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, delete

from apps.api.config import get_settings
from apps.api.db.session import engine
from apps.api.db.models import Run, RunStatus, RateLimitBucket
from apps.api.services.diagnostics_sink import WorkerSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_expired_runs")
settings = get_settings()


def cleanup_expired_runs(retention_hours: int | None = None) -> int:
    """Marks anonymous runs older than retention_hours as EXPIRED, clears article content, deletes Cloudinary assets, and purges rate limit buckets."""
    hours = retention_hours or settings.ANONYMOUS_RETENTION_HOURS
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    with WorkerSessionLocal() as session:
        # Select expired anonymous runs to gather asset public_ids
        expired_runs = session.scalars(
            select(Run).where(
                Run.user_id.is_(None),
                Run.anonymous_session_id.isnot(None),
                Run.created_at < cutoff,
                Run.status != RunStatus.EXPIRED.value,
            )
        ).all()

        cloudinary_pids: list[str] = []
        for run in expired_runs:
            assets = run.article_assets or []
            for asset in assets:
                if isinstance(asset, dict) and asset.get("public_id") and not asset["public_id"].startswith("local:"):
                    cloudinary_pids.append(asset["public_id"])
            run.status = RunStatus.EXPIRED.value
            run.expires_at = now
            run.article_markdown = None
            run.article_assets = None

        # Purge expired rate limit buckets
        session.execute(
            delete(RateLimitBucket).where(RateLimitBucket.expires_at < now)
        )

        session.commit()
        count = len(expired_runs)

        if cloudinary_pids:
            try:
                from blog_agent.services.cloudinary_storage import delete_cloudinary_assets
                delete_cloudinary_assets(cloudinary_pids)
            except Exception as exc:
                logger.warning(f"Failed to delete Cloudinary assets for expired runs: {exc}")

        logger.info(f"Marked {count} anonymous runs older than {hours} hours as expired, purged expired rate limit buckets.")
        return count


if __name__ == "__main__":
    cleanup_expired_runs()
