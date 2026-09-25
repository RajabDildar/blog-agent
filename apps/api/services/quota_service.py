"""Quota and abuse enforcement for authenticated and anonymous generation requests."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import redis
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db.models import Run, RunStatus
from apps.api.queue import get_redis_connection

settings = get_settings()


class QuotaExceededError(Exception):
    """Raised when user or anonymous quota or rate limit is exceeded."""
    pass


def get_current_utc_day_start() -> datetime:
    """Returns midnight UTC for the current day."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def check_and_increment_abuse_limit(
    client_ip: Optional[str],
    redis_conn: Optional[redis.Redis] = None,
) -> None:
    """
    Enforces INTENT_REQUESTS_PER_IP_PER_HOUR counter in Redis.
    Limits rapid provider abuse on run creation and HITL input submission.
    """
    if not client_ip:
        return

    r = redis_conn or get_redis_connection()
    key = f"abuse:ip_intent_hour:{client_ip}"
    try:
        current = r.incr(key)
        if current == 1:
            r.expire(key, 3600)

        if current > settings.INTENT_REQUESTS_PER_IP_PER_HOUR:
            raise QuotaExceededError(
                f"Rate limit exceeded: maximum {settings.INTENT_REQUESTS_PER_IP_PER_HOUR} requests per hour allowed from this IP."
            )
    except redis.RedisError:
        # If Redis is unavailable during testing/transient, do not hard-block unless required
        pass


def check_pre_generation_quota(
    db: Session,
    user_id: Optional[str] = None,
    anonymous_session_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    redis_conn: Optional[redis.Redis] = None,
) -> None:
    """
    Fast pre-check at POST /runs boundary to reject requests early if quota is already exhausted.
    """
    utc_today = get_current_utc_day_start()

    if user_id:
        # Authenticated quota: max runs with generation_started_at today
        count = db.scalar(
            select(func.count(Run.id)).where(
                Run.user_id == user_id,
                Run.generation_started_at >= utc_today,
            )
        ) or 0

        if count >= settings.AUTHENTICATED_DAILY_RUN_LIMIT:
            raise QuotaExceededError(
                f"Daily generation limit reached ({settings.AUTHENTICATED_DAILY_RUN_LIMIT} articles per day). Resets at midnight UTC."
            )

    elif anonymous_session_id:
        # Anonymous quota: max 1 generated article per anonymous session
        has_started = db.scalar(
            select(func.count(Run.id)).where(
                Run.anonymous_session_id == anonymous_session_id,
                Run.generation_started_at.isnot(None),
            )
        ) or 0

        if has_started >= 1:
            raise QuotaExceededError(
                "Anonymous article generation limit reached (1 article). Please sign in to generate more articles."
            )

        # IP backstop check
        if client_ip:
            r = redis_conn or get_redis_connection()
            ip_key = f"quota:anon_ip_day:{client_ip}:{utc_today.strftime('%Y%m%d')}"
            try:
                ip_count = int(r.get(ip_key) or 0)
                if ip_count >= settings.ANONYMOUS_DAILY_IP_LIMIT:
                    raise QuotaExceededError(
                        f"Daily anonymous limit for this IP reached ({settings.ANONYMOUS_DAILY_IP_LIMIT} articles). Please sign in."
                    )
            except redis.RedisError:
                pass


def reserve_generation_quota_atomic(
    db: Session,
    run_id: str,
    client_ip: Optional[str] = None,
    redis_conn: Optional[redis.Redis] = None,
) -> bool:
    """
    Transactionally enforces quota reservation when topic is finalized before article generation.
    Returns True if quota was reserved, or False if quota was exceeded.
    """
    utc_today = get_current_utc_day_start()

    # Lock the run row
    run = db.scalar(
        select(Run).where(Run.id == run_id).with_for_update()
    )
    if not run:
        return False

    if run.generation_started_at is not None:
        # Already reserved
        return True

    if run.user_id:
        count = db.scalar(
            select(func.count(Run.id)).where(
                Run.user_id == run.user_id,
                Run.generation_started_at >= utc_today,
            )
        ) or 0

        if count >= settings.AUTHENTICATED_DAILY_RUN_LIMIT:
            run.status = RunStatus.FAILED.value
            run.error_code = "quota_exceeded"
            run.error_message = (
                f"Daily generation limit of {settings.AUTHENTICATED_DAILY_RUN_LIMIT} reached for this account."
            )
            db.commit()
            return False

    elif run.anonymous_session_id:
        has_started = db.scalar(
            select(func.count(Run.id)).where(
                Run.anonymous_session_id == run.anonymous_session_id,
                Run.generation_started_at.isnot(None),
            )
        ) or 0

        if has_started >= 1:
            run.status = RunStatus.FAILED.value
            run.error_code = "quota_exceeded"
            run.error_message = (
                "Anonymous generation limit reached (1 article). Please sign in."
            )
            db.commit()
            return False

        if client_ip:
            r = redis_conn or get_redis_connection()
            ip_key = f"quota:anon_ip_day:{client_ip}:{utc_today.strftime('%Y%m%d')}"
            try:
                ip_count = r.incr(ip_key)
                if ip_count == 1:
                    r.expire(ip_key, 86400)
                if ip_count > settings.ANONYMOUS_DAILY_IP_LIMIT:
                    run.status = RunStatus.FAILED.value
                    run.error_code = "quota_exceeded"
                    run.error_message = f"Daily anonymous limit reached for this IP ({settings.ANONYMOUS_DAILY_IP_LIMIT})."
                    db.commit()
                    return False
            except redis.RedisError:
                pass

    # Reserve slot
    run.generation_started_at = datetime.now(timezone.utc)
    db.commit()
    return True
