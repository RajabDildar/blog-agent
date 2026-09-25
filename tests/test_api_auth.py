"""Unit tests for authentication, Google token verification, and sessions."""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.config import get_settings
from apps.api.db.models import User, Session as DbSession
from apps.api.auth.google import verify_google_credential, GoogleAuthError
from apps.api.auth.sessions import (
    hash_token,
    generate_session_token,
    create_session,
    get_session_and_user_by_token,
    revoke_session,
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

def test_google_verify_success():
    client_id = "test-client-id"
    fake_credential = "fake.jwt.token"
    mock_payload = {
        "iss": "https://accounts.google.com",
        "sub": "google-user-12345",
        "email": "testuser@gmail.com",
        "name": "Test User",
        "picture": "https://example.com/avatar.jpg",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_payload):
        payload = verify_google_credential(fake_credential, client_id=client_id)
        assert payload.google_sub == "google-user-12345"
        assert payload.email == "testuser@gmail.com"
        assert payload.display_name == "Test User"
        assert payload.avatar_url == "https://example.com/avatar.jpg"

def test_google_verify_invalid_issuer():
    client_id = "test-client-id"
    fake_credential = "fake.jwt.token"
    mock_payload = {
        "iss": "https://malicious-issuer.com",
        "sub": "bad-user",
        "email": "bad@example.com",
    }

    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_payload):
        with pytest.raises(GoogleAuthError, match="Invalid token issuer"):
            verify_google_credential(fake_credential, client_id=client_id)

def test_google_verify_missing_sub():
    client_id = "test-client-id"
    mock_payload = {
        "iss": "https://accounts.google.com",
        "email": "missing-sub@example.com",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_payload):
        with pytest.raises(GoogleAuthError, match="missing 'sub'"):
            verify_google_credential("token", client_id=client_id)

def test_session_lifecycle_and_hashing(db):
    user = User(
        google_sub=f"sub-{uuid.uuid4().hex}",
        email="session_test@example.com",
        display_name="Session Tester",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create session
    session_row, raw_token = create_session(db, user_id=user.id, max_age_seconds=3600)
    assert session_row.id is not None
    assert session_row.token_hash == hash_token(raw_token)
    assert session_row.token_hash != raw_token

    # Lookup by raw token
    looked_up_session, looked_up_user = get_session_and_user_by_token(db, raw_token)
    assert looked_up_session is not None
    assert looked_up_user is not None
    assert looked_up_user.id == user.id

    # Revoke session
    revoked = revoke_session(db, raw_token)
    assert revoked is True

    # After revocation, lookup should return None
    none_session, none_user = get_session_and_user_by_token(db, raw_token)
    assert none_session is None
    assert none_user is None

def test_expired_session_handling(db):
    user = User(
        google_sub=f"sub-{uuid.uuid4().hex}",
        email="expired_test@example.com",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    raw_token = generate_session_token()
    token_h = hash_token(raw_token)
    expired_time = datetime.now(timezone.utc) - timedelta(hours=1)

    expired_session = DbSession(
        user_id=user.id,
        token_hash=token_h,
        created_at=expired_time - timedelta(days=1),
        expires_at=expired_time,
        last_used_at=expired_time,
    )
    db.add(expired_session)
    db.commit()

    # Expired session lookup should return (None, None) and delete expired row
    session_res, user_res = get_session_and_user_by_token(db, raw_token)
    assert session_res is None
    assert user_res is None
