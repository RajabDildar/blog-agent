"""Unit tests for RunService domain invariants and authorization rules."""
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.config import get_settings
from apps.api.db.models import User, Run, RunStatus, RunVisibility
from apps.api.services.run_service import (
    create_run,
    get_run_by_id,
    list_runs,
    update_run_visibility,
    update_run_featured,
    get_gallery,
    get_featured,
    RunInvariantError,
    RunNotFoundError,
)

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

def create_user(db, is_admin=False) -> User:
    user = User(
        google_sub=f"sub-{uuid.uuid4().hex}",
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Test User",
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def test_run_creation_requires_identity(db):
    with pytest.raises(RunInvariantError, match="must have either user_id or anonymous_session_id"):
        create_run(db, original_input="Topic without identity", user_id=None, anonymous_session_id=None)

    with pytest.raises(RunInvariantError, match="cannot be empty"):
        user = create_user(db)
        create_run(db, original_input="   ", user_id=user.id)

def test_run_creation_initial_state(db):
    user = create_user(db)
    run = create_run(db, original_input="Deep Dive into Raft", user_id=user.id)
    assert run.id is not None
    assert run.user_id == user.id
    assert run.original_input == "Deep Dive into Raft"
    assert run.topic is None
    assert run.status == RunStatus.QUEUED.value
    assert run.visibility == RunVisibility.PRIVATE.value
    assert run.featured is False

def test_strict_ownership_access(db):
    user_a = create_user(db)
    user_b = create_user(db)
    anon_a = str(uuid.uuid4())
    anon_b = str(uuid.uuid4())

    run_a = create_run(db, original_input="User A private run", user_id=user_a.id)
    run_anon = create_run(db, original_input="Anon A private run", anonymous_session_id=anon_a)

    # User A can read own run
    assert get_run_by_id(db, run_a.id, user_id=user_a.id) is not None

    # User B cannot read User A's private run
    assert get_run_by_id(db, run_a.id, user_id=user_b.id) is None

    # Anon B cannot read Anon A's private run
    assert get_run_by_id(db, run_anon.id, anonymous_session_id=anon_b) is None

    # Admin cannot read User A's private run (roadmap 11.10 rule)
    assert get_run_by_id(db, run_a.id, is_admin=True) is None

def test_visibility_invariants(db):
    user = create_user(db)
    run = create_run(db, original_input="Running article", user_id=user.id)

    # Incomplete run cannot be made public
    with pytest.raises(RunInvariantError, match="Only completed runs can be made public"):
        update_run_visibility(db, run.id, RunVisibility.PUBLIC, user_id=user.id)

    # Complete the run
    run.status = RunStatus.COMPLETED.value
    run.completed_at = datetime.now(timezone.utc)
    db.commit()

    # Now it can be made public
    updated = update_run_visibility(db, run.id, RunVisibility.PUBLIC, user_id=user.id)
    assert updated.visibility == RunVisibility.PUBLIC.value

    # Public completed run is accessible by anyone
    assert get_run_by_id(db, run.id) is not None

def test_featured_invariants(db):
    user = create_user(db)
    admin = create_user(db, is_admin=True)
    run = create_run(db, original_input="Article to feature", user_id=user.id)

    # Non-admin cannot feature
    with pytest.raises(PermissionError, match="Administrator privileges required"):
        update_run_featured(db, run.id, featured=True, is_admin=False)

    # Admin cannot feature private or non-completed run
    with pytest.raises(RunInvariantError, match="Cannot feature a private run"):
        update_run_featured(db, run.id, featured=True, is_admin=True)

    # Make run completed but private
    run.status = RunStatus.COMPLETED.value
    run.completed_at = datetime.now(timezone.utc)
    db.commit()

    with pytest.raises(RunInvariantError, match="Cannot feature a private run"):
        update_run_featured(db, run.id, featured=True, is_admin=True)

    # Make run public
    run.visibility = RunVisibility.PUBLIC.value
    db.commit()

    # Admin can now feature
    featured_run = update_run_featured(db, run.id, featured=True, is_admin=True)
    assert featured_run.featured is True

    # Switching visibility to private automatically unfeatures
    privatized = update_run_visibility(db, run.id, RunVisibility.PRIVATE, user_id=user.id)
    assert privatized.visibility == RunVisibility.PRIVATE.value
    assert privatized.featured is False

def test_gallery_and_featured_queries(db):
    user = create_user(db)
    run = create_run(db, original_input="Gallery candidate", user_id=user.id)
    run.status = RunStatus.COMPLETED.value
    run.visibility = RunVisibility.PUBLIC.value
    run.featured = True
    run.completed_at = datetime.now(timezone.utc)
    db.commit()

    gallery = get_gallery(db)
    assert any(r.id == run.id for r in gallery)

    featured = get_featured(db)
    assert any(r.id == run.id for r in featured)
