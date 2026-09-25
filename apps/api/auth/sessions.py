"""Opaque session management with SHA-256 token hashing."""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from apps.api.config import get_settings
from apps.api.db.models import Session, User

settings = get_settings()


def hash_token(raw_token: str) -> str:
    """Computes SHA-256 hash of raw session token for database lookup."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_session_token() -> str:
    """Generates a cryptographically strong opaque session token."""
    return secrets.token_urlsafe(32)


def create_session(
    db: DbSession,
    user_id: str,
    max_age_seconds: Optional[int] = None,
) -> Tuple[Session, str]:
    """
    Creates an opaque session record in the database.
    Returns the session model instance and the raw unhashed token to send to the client.
    """
    if max_age_seconds is None:
        max_age_seconds = settings.SESSION_MAX_AGE_SECONDS

    raw_token = generate_session_token()
    token_h = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=max_age_seconds)

    session = Session(
        user_id=user_id,
        token_hash=token_h,
        created_at=now,
        expires_at=expires_at,
        last_used_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, raw_token


def get_session_and_user_by_token(
    db: DbSession,
    raw_token: str,
) -> Tuple[Optional[Session], Optional[User]]:
    """
    Looks up an active session by raw token.
    Updates `last_used_at` if found and not expired.
    Returns (None, None) if missing or expired.
    """
    if not raw_token:
        return None, None

    token_h = hash_token(raw_token)
    now = datetime.now(timezone.utc)

    stmt = select(Session).where(Session.token_hash == token_h)
    session = db.scalar(stmt)
    if not session:
        return None, None

    # Check expiration
    if session.expires_at <= now:
        db.delete(session)
        db.commit()
        return None, None

    # Update last_used_at
    session.last_used_at = now
    db.commit()
    return session, session.user


def revoke_session(db: DbSession, raw_token: str) -> bool:
    """Revokes a session by deleting its record."""
    if not raw_token:
        return False

    token_h = hash_token(raw_token)
    stmt = select(Session).where(Session.token_hash == token_h)
    session = db.scalar(stmt)
    if session:
        db.delete(session)
        db.commit()
        return True
    return False


def set_session_cookie(
    response: Response,
    raw_token: str,
    max_age_seconds: Optional[int] = None,
    secure: Optional[bool] = None,
) -> None:
    """Sets the HttpOnly session cookie."""
    if max_age_seconds is None:
        max_age_seconds = settings.SESSION_MAX_AGE_SECONDS
    if secure is None:
        secure = settings.cookie_secure

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=max_age_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Clears the session cookie from the browser."""
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
    )


def set_anonymous_cookie(
    response: Response,
    anonymous_id: str,
    secure: Optional[bool] = None,
) -> None:
    """Sets the anonymous user cookie."""
    if secure is None:
        secure = settings.cookie_secure

    # 30-day retention for anonymous cookie
    max_age = 30 * 24 * 3600
    response.set_cookie(
        key=settings.ANONYMOUS_COOKIE_NAME,
        value=anonymous_id,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def get_or_create_anonymous_id(
    request: Request,
    response: Optional[Response] = None,
    secure: Optional[bool] = None,
) -> str:
    """
    Extracts the anonymous cookie or creates a new opaque UUID identifier.
    If a response object is provided and a new identifier is created, sets the cookie.
    """
    cookie_id = request.cookies.get(settings.ANONYMOUS_COOKIE_NAME)
    if cookie_id and len(cookie_id.strip()) > 0:
        return cookie_id.strip()

    new_id = str(uuid.uuid4())
    if response is not None:
        set_anonymous_cookie(response, new_id, secure=secure)
    return new_id
