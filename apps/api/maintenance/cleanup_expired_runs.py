"""Idempotent maintenance command to expire or clean up anonymous runs exceeding retention hours."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update

from apps.api.config import get_settings
from apps.api.db.session import engine
from apps.api.db.models import Run, RunStatus
from apps.api.services.diagnostics_sink import WorkerSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_expired_runs")
settings = get_settings()


def cleanup_expired_runs(retention_hours: int | None = None) -> int:
    """Marks anonymous runs older than retention_hours as EXPIRED."""
    hours = retention_hours or settings.ANONYMOUS_RETENTION_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

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
                expires_at=datetime.now(timezone.utc),
            )
        )
        result = session.execute(stmt)
        session.commit()
        count = result.rowcount
        logger.info(f"Marked {count} anonymous runs older than {hours} hours as expired.")
        return count


if __name__ == "__main__":
    cleanup_expired_runs()
