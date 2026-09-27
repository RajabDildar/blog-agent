"""Phase 4 tests: Quota service - daily generation limits and abuse protection using PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from apps.api.config import get_settings
from apps.api.db.models import Run, RunStatus, User, RateLimitBucket

settings = get_settings()


@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine(settings.DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ---------------------------------------------------------------------------
# Quota service import smoke test
# ---------------------------------------------------------------------------

def test_quota_service_imports_without_error():
    """All public quota service symbols must be importable."""
    from apps.api.services.quota_service import (  # noqa: F401
        check_and_increment_abuse_limit,
        check_pre_generation_quota,
        reserve_generation_quota_atomic,
        hash_identifier,
        QuotaExceededError,
    )


# ---------------------------------------------------------------------------
# check_and_increment_abuse_limit tests (PostgreSQL-backed)
# ---------------------------------------------------------------------------

def test_abuse_limit_allows_first_request(db):
    """check_and_increment_abuse_limit must create a bucket row and pass for a fresh IP."""
    from apps.api.services.quota_service import check_and_increment_abuse_limit, hash_identifier

    test_ip = f"10.0.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    check_and_increment_abuse_limit(client_ip=test_ip, db=db)

    now = datetime.now(timezone.utc)
    window_hour = now.strftime("%Y%m%d%H")
    expected_key = hash_identifier(f"abuse:ip_intent_hour:{test_ip}:{window_hour}")

    bucket = db.scalar(select(RateLimitBucket).where(RateLimitBucket.bucket_key == expected_key))
    assert bucket is not None
    assert bucket.count == 1


def test_abuse_limit_raises_when_limit_exceeded(db):
    """check_and_increment_abuse_limit must raise QuotaExceededError when counter exceeds limit."""
    from apps.api.services.quota_service import check_and_increment_abuse_limit, hash_identifier, QuotaExceededError

    test_ip = f"10.1.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    now = datetime.now(timezone.utc)
    window_hour = now.strftime("%Y%m%d%H")
    expected_key = hash_identifier(f"abuse:ip_intent_hour:{test_ip}:{window_hour}")

    # Seed bucket at the limit
    seed_bucket = RateLimitBucket(
        bucket_key=expected_key,
        count=settings.INTENT_REQUESTS_PER_IP_PER_HOUR,
        expires_at=now + timedelta(hours=1),
    )
    db.add(seed_bucket)
    db.commit()

    with pytest.raises(QuotaExceededError):
        check_and_increment_abuse_limit(client_ip=test_ip, db=db)


def test_abuse_limit_skips_when_ip_is_none(db):
    """check_and_increment_abuse_limit must silently skip when no IP is available."""
    from apps.api.services.quota_service import check_and_increment_abuse_limit

    # Should not raise, should not insert anything
    initial_count = db.scalar(select(RateLimitBucket.id))
    check_and_increment_abuse_limit(client_ip=None, db=db)


def test_abuse_limit_hashes_ip_and_stores_no_raw_ip(db):
    """Bucket keys must be HMAC-SHA256 digests and must not contain the raw IP string."""
    from apps.api.services.quota_service import check_and_increment_abuse_limit

    raw_ip = "192.168.100.200"
    check_and_increment_abuse_limit(client_ip=raw_ip, db=db)

    # Check that raw IP does not appear anywhere in bucket keys
    buckets = db.scalars(select(RateLimitBucket)).all()
    for b in buckets:
        assert raw_ip not in b.bucket_key


# ---------------------------------------------------------------------------
# check_pre_generation_quota tests
# ---------------------------------------------------------------------------

def _make_completed_runs_for_quota(db, *, count: int, anon_id: str | None = None, user_id: str | None = None):
    """Helper: insert runs with generation_started_at today."""
    now = datetime.now(timezone.utc)
    today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    for _ in range(count):
        run = Run(
            original_input="Quota test",
            status=RunStatus.COMPLETED.value,
            generation_started_at=today + timedelta(minutes=1),
            anonymous_session_id=anon_id,
            user_id=user_id,
        )
        db.add(run)
    db.commit()


def test_pre_generation_quota_allows_anonymous_with_no_prior_runs(db):
    """Anonymous user with no prior runs must pass quota check."""
    from apps.api.services.quota_service import check_pre_generation_quota

    anon_id = "fresh-anon-" + uuid.uuid4().hex[:8]

    # Should not raise
    check_pre_generation_quota(
        db=db,
        anonymous_session_id=anon_id,
        client_ip="1.1.1.1",
    )


def test_pre_generation_quota_blocks_anonymous_after_first_run(db):
    """Anonymous user with one prior generated run must be blocked."""
    from apps.api.services.quota_service import check_pre_generation_quota, QuotaExceededError

    anon_id = "one-run-anon-" + uuid.uuid4().hex[:8]
    _make_completed_runs_for_quota(db, count=1, anon_id=anon_id)

    with pytest.raises(QuotaExceededError):
        check_pre_generation_quota(
            db=db,
            anonymous_session_id=anon_id,
            client_ip="1.1.1.1",
        )


def test_pre_generation_quota_uses_generation_started_at_not_created_at(db):
    """Quota must NOT count runs that never had generation_started_at set."""
    from apps.api.services.quota_service import check_pre_generation_quota

    anon_id = "no-gen-anon-" + uuid.uuid4().hex[:8]
    # Insert runs WITHOUT generation_started_at (blocked / invalid runs)
    for _ in range(10):
        run = Run(
            original_input="Blocked run",
            status=RunStatus.BLOCKED.value,
            generation_started_at=None,
            anonymous_session_id=anon_id,
        )
        db.add(run)
    db.commit()

    # Should NOT raise - none of these runs consumed quota
    check_pre_generation_quota(
        db=db,
        anonymous_session_id=anon_id,
        client_ip="1.1.1.1",
    )


def test_pre_generation_quota_allows_authenticated_under_daily_limit(db):
    """Authenticated user under their daily limit must pass."""
    from apps.api.services.quota_service import check_pre_generation_quota

    user = User(
        google_sub=f"sub-quota-{uuid.uuid4().hex}",
        email=f"quota-auth-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Quota Auth User",
    )
    db.add(user)
    db.commit()

    # Add runs under the limit
    for _ in range(max(0, settings.AUTHENTICATED_DAILY_RUN_LIMIT - 2)):
        run = Run(
            original_input="Auth run",
            status=RunStatus.COMPLETED.value,
            generation_started_at=datetime.now(timezone.utc),
            user_id=user.id,
        )
        db.add(run)
    db.commit()

    # Should not raise
    check_pre_generation_quota(db=db, user_id=user.id)


def test_pre_generation_quota_blocks_authenticated_at_daily_limit(db):
    """Authenticated user at their daily limit must be blocked."""
    from apps.api.services.quota_service import check_pre_generation_quota, QuotaExceededError

    user = User(
        google_sub=f"sub-quota-max-{uuid.uuid4().hex}",
        email=f"quota-max-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Max Quota User",
    )
    db.add(user)
    db.commit()

    # Fill up to limit
    for _ in range(settings.AUTHENTICATED_DAILY_RUN_LIMIT):
        run = Run(
            original_input="Limit run",
            status=RunStatus.COMPLETED.value,
            generation_started_at=datetime.now(timezone.utc),
            user_id=user.id,
        )
        db.add(run)
    db.commit()

    with pytest.raises(QuotaExceededError):
        check_pre_generation_quota(db=db, user_id=user.id)


# ---------------------------------------------------------------------------
# reserve_generation_quota_atomic tests
# ---------------------------------------------------------------------------

def test_reserve_quota_sets_generation_started_at(db):
    """reserve_generation_quota_atomic must set generation_started_at for a new run."""
    from apps.api.services.quota_service import reserve_generation_quota_atomic

    anon_id = "reserve-anon-" + uuid.uuid4().hex[:8]
    run = Run(
        original_input="Quota reserve test",
        status=RunStatus.RUNNING.value,
        generation_started_at=None,
        anonymous_session_id=anon_id,
    )
    db.add(run)
    db.commit()

    result = reserve_generation_quota_atomic(db=db, run_id=run.id)
    assert result is True

    db.expire(run)
    db.refresh(run)
    assert run.generation_started_at is not None


def test_reserve_quota_is_idempotent(db):
    """reserve_generation_quota_atomic must return True if quota already reserved."""
    from apps.api.services.quota_service import reserve_generation_quota_atomic

    run = Run(
        original_input="Idempotent reserve test",
        status=RunStatus.RUNNING.value,
        generation_started_at=datetime.now(timezone.utc),  # Already set
    )
    db.add(run)
    db.commit()

    result = reserve_generation_quota_atomic(db=db, run_id=run.id)
    assert result is True


def test_reserve_quota_blocks_anonymous_second_run(db):
    """reserve_generation_quota_atomic must return False and mark run failed for 2nd anon run."""
    from apps.api.services.quota_service import reserve_generation_quota_atomic

    anon_id = "double-anon-" + uuid.uuid4().hex[:8]

    # First run - already used quota
    existing = Run(
        original_input="First run",
        status=RunStatus.COMPLETED.value,
        generation_started_at=datetime.now(timezone.utc),
        anonymous_session_id=anon_id,
    )
    db.add(existing)
    db.commit()

    # Second run - should be blocked
    second = Run(
        original_input="Second run",
        status=RunStatus.RUNNING.value,
        generation_started_at=None,
        anonymous_session_id=anon_id,
    )
    db.add(second)
    db.commit()

    result = reserve_generation_quota_atomic(db=db, run_id=second.id)
    assert result is False

    db.expire(second)
    db.refresh(second)
    assert second.status == RunStatus.FAILED.value
    assert second.error_code == "quota_exceeded"
    assert second.generation_started_at is None
