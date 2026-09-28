"""Quota and abuse enforcement for authenticated and anonymous generation requests."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db.models import Run, RunStatus, RateLimitBucket
from apps.api.services.diagnostics_sink import WorkerSessionLocal

settings = get_settings()


class QuotaExceededError(Exception):
    """Raised when user or anonymous quota or rate limit is exceeded."""
    pass


def get_current_utc_day_start() -> datetime:
    """Returns midnight UTC for the current day."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def hash_identifier(raw_value: str, salt: Optional[str] = None) -> str:
    """Produces a secure HMAC-SHA256 hex digest so raw IPs are never stored."""
    secret = (salt or settings.SESSION_SECRET_KEY).encode("utf-8")
    return hmac.new(secret, raw_value.encode("utf-8"), hashlib.sha256).hexdigest()


def check_and_increment_abuse_limit(
    client_ip: Optional[str],
    db: Optional[Session] = None,
) -> None:
    """
    Enforces INTENT_REQUESTS_PER_IP_PER_HOUR counter in PostgreSQL rate_limit_buckets.
    Limits rapid provider abuse on run creation and HITL input submission without Redis.
    """
    if not client_ip:
        return

    now = datetime.now(timezone.utc)
    window_hour = now.strftime("%Y%m%d%H")
    bucket_key = hash_identifier(f"abuse:ip_intent_hour:{client_ip}:{window_hour}")
    expires_at = now + timedelta(hours=1)

    def _execute(session: Session) -> None:
        bucket = session.scalar(
            select(RateLimitBucket)
            .where(RateLimitBucket.bucket_key == bucket_key)
            .with_for_update()
        )
        if bucket:
            bucket.count += 1
            current = bucket.count
        else:
            new_bucket = RateLimitBucket(
                bucket_key=bucket_key,
                count=1,
                expires_at=expires_at,
            )
            session.add(new_bucket)
            current = 1
        session.commit()

        if current > settings.INTENT_REQUESTS_PER_IP_PER_HOUR:
            raise QuotaExceededError(
                f"Rate limit exceeded: maximum {settings.INTENT_REQUESTS_PER_IP_PER_HOUR} requests per hour allowed from this IP."
            )

    if db is not None:
        _execute(db)
    else:
        with WorkerSessionLocal() as session:
            _execute(session)


def check_pre_generation_quota(
    db: Session,
    user_id: Optional[str] = None,
    anonymous_session_id: Optional[str] = None,
    client_ip: Optional[str] = None,
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

        # IP backstop check in PostgreSQL
        if client_ip:
            day_str = utc_today.strftime("%Y%m%d")
            ip_bucket_key = hash_identifier(f"quota:anon_ip_day:{client_ip}:{day_str}")
            bucket = db.scalar(
                select(RateLimitBucket).where(RateLimitBucket.bucket_key == ip_bucket_key)
            )
            if bucket and bucket.count >= settings.ANONYMOUS_DAILY_IP_LIMIT:
                raise QuotaExceededError(
                    f"Daily anonymous limit for this IP reached ({settings.ANONYMOUS_DAILY_IP_LIMIT} articles). Please sign in."
                )


def reserve_generation_quota_atomic(
    db: Session,
    run_id: str,
    client_ip: Optional[str] = None,
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

        effective_ip_identifier = client_ip or run.client_ip_hash
        if effective_ip_identifier:
            day_str = utc_today.strftime("%Y%m%d")
            ip_bucket_key = hash_identifier(f"quota:anon_ip_day:{effective_ip_identifier}:{day_str}")
            bucket = db.scalar(
                select(RateLimitBucket)
                .where(RateLimitBucket.bucket_key == ip_bucket_key)
                .with_for_update()
            )
            if bucket:
                bucket.count += 1
                current_ip_count = bucket.count
            else:
                new_bucket = RateLimitBucket(
                    bucket_key=ip_bucket_key,
                    count=1,
                    expires_at=utc_today + timedelta(days=1),
                )
                db.add(new_bucket)
                current_ip_count = 1

            if current_ip_count > settings.ANONYMOUS_DAILY_IP_LIMIT:
                run.status = RunStatus.FAILED.value
                run.error_code = "quota_exceeded"
                run.error_message = f"Daily anonymous limit reached for this IP ({settings.ANONYMOUS_DAILY_IP_LIMIT})."
                db.commit()
                return False

    # Reserve slot
    run.generation_started_at = datetime.now(timezone.utc)
    db.commit()
    return True
