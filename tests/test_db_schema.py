"""Unit and integration tests for PostgreSQL database schema and models."""
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from apps.api.config import get_settings
from apps.api.db.base import Base
from apps.api.db.models import User, Session as DbSession, Run, RunStatus, RunVisibility

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

def test_user_creation_and_unique_google_sub(db: Session):
    unique_sub = f"google-sub-{uuid.uuid4().hex}"
    user = User(
        google_sub=unique_sub,
        email="test@example.com",
        display_name="Test User",
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    assert user.id is not None
    assert user.google_sub == unique_sub
    assert user.created_at is not None
    assert user.updated_at is not None

    # Duplicate google_sub must fail with IntegrityError
    dup_user = User(
        google_sub=unique_sub,
        email="another@example.com",
    )
    db.add(dup_user)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

def test_session_token_hash_uniqueness_and_cascade(db: Session):
    user = User(
        google_sub=f"google-sub-{uuid.uuid4().hex}",
        email="session_user@example.com",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token_hash = uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    session = DbSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    assert session.id is not None
    assert session.user_id == user.id

    # Duplicate token_hash must fail
    dup_session = DbSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(dup_session)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Cascade delete check
    db.delete(user)
    db.commit()
    deleted_session = db.scalar(select(DbSession).where(DbSession.id == session.id))
    assert deleted_session is None

def test_run_creation_and_vocabulary(db: Session):
    expected_vocabulary = {
        "queued", "running", "awaiting_input", "paused", "completed",
        "failed", "blocked", "invalid", "cancelled", "expired"
    }
    actual_vocabulary = {status.value for status in RunStatus}
    assert actual_vocabulary == expected_vocabulary

    run = Run(
        original_input="Explain quantum algorithms",
        topic=None,
        status=RunStatus.QUEUED.value,
        visibility=RunVisibility.PRIVATE.value,
        featured=False,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    assert run.id is not None
    assert run.original_input == "Explain quantum algorithms"
    assert run.topic is None
    assert run.status == "queued"
    assert run.visibility == "private"
    assert run.featured is False
    assert run.created_at is not None


def test_run_event_creation_and_sequence_uniqueness(db: Session):
    from apps.api.db.models import RunEvent

    run = Run(
        original_input="Test event pipeline",
        status=RunStatus.RUNNING.value,
    )
    db.add(run)
    db.commit()

    event1 = RunEvent(
        run_id=run.id,
        sequence=1,
        event_type="run_queued",
        stage=None,
        message="Run enqueued",
        payload={"info": "started"},
    )
    event2 = RunEvent(
        run_id=run.id,
        sequence=2,
        event_type="node_started",
        stage="intent_gateway",
        message="Intent gateway started",
        payload=None,
    )
    db.add_all([event1, event2])
    db.commit()

    db.refresh(run)
    assert len(run.events) == 2
    assert run.events[0].sequence == 1
    assert run.events[0].event_type == "run_queued"
    assert run.events[1].sequence == 2
    assert run.events[1].event_type == "node_started"

    # Duplicate sequence for the same run must raise IntegrityError
    dup_event = RunEvent(
        run_id=run.id,
        sequence=1,
        event_type="duplicate_event",
    )
    db.add(dup_event)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

