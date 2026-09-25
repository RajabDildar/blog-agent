"""Unit tests for anonymous run claim service."""
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.config import get_settings
from apps.api.db.models import User, Run, RunStatus
from apps.api.services.run_service import create_run
from apps.api.services.claim_service import claim_anonymous_runs

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

def create_user(db) -> User:
    user = User(
        google_sub=f"sub-{uuid.uuid4().hex}",
        email=f"claim_user_{uuid.uuid4().hex[:8]}@example.com",
        display_name="Claim User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def test_anonymous_run_claiming(db):
    user = create_user(db)
    anon_session_id = str(uuid.uuid4())
    other_anon_id = str(uuid.uuid4())

    # Create 2 runs for this anonymous session
    run1 = create_run(db, original_input="Run 1 by anonymous user", anonymous_session_id=anon_session_id)
    run2 = create_run(db, original_input="Run 2 by anonymous user", anonymous_session_id=anon_session_id)
    # Create 1 run for an unrelated anonymous session
    run3 = create_run(db, original_input="Run by different anonymous user", anonymous_session_id=other_anon_id)

    run1_id = run1.id
    run2_id = run2.id
    run3_id = run3.id

    # Claim runs for user
    claimed = claim_anonymous_runs(db, anonymous_session_id=anon_session_id, user_id=user.id)
    assert len(claimed) == 2

    # Check transferred runs: IDs unchanged, owned by user, anon id cleared
    db.refresh(run1)
    db.refresh(run2)
    db.refresh(run3)

    assert run1.id == run1_id
    assert run1.user_id == user.id
    assert run1.anonymous_session_id is None

    assert run2.id == run2_id
    assert run2.user_id == user.id
    assert run2.anonymous_session_id is None

    # Unrelated run is untouched
    assert run3.id == run3_id
    assert run3.user_id is None
    assert run3.anonymous_session_id == other_anon_id
