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
    """Marks anonymous runs older than retention_hours as EXPIRED and purges expired rate limit buckets."""
    hours = retention_hours or settings.ANONYMOUS_RETENTION_HOURS
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    with WorkerSessionLocal() as session:
        # Find active or terminal anonymous runs created before cutoff that are not already expired
        stmt = (
            update(Run)
            .where(
                Run.user_id.is_(None),
                Run.anonymous_session_id.isnot(None),
                Run.created_at < cutoff,
                Run.status != RunStatus.EXPIRED.value,
            )
            .values(
                status=RunStatus.EXPIRED.value,
                expires_at=now,
            )
        )
        result = session.execute(stmt)

        # Also purge expired rate limit buckets
        session.execute(
            delete(RateLimitBucket).where(RateLimitBucket.expires_at < now)
        )

        session.commit()
        count = result.rowcount
        logger.info(f"Marked {count} anonymous runs older than {hours} hours as expired, purged expired rate limit buckets.")
        return count


if __name__ == "__main__":
    cleanup_expired_runs()
