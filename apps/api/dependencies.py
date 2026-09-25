"""FastAPI route dependencies for database, authentication, anonymous identity, and CSRF."""
from typing import Optional, Generator
from fastapi import Depends, Request, Response, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db.session import SessionLocal
from apps.api.db.models import User
from apps.api.auth.sessions import get_session_and_user_by_token, get_or_create_anonymous_id
from apps.api.auth.csrf import validate_csrf

settings = get_settings()


def get_db() -> Generator[Session, None, None]:
    """Yields a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Extracts user from opaque session cookie if valid and not expired.
    Returns None if unauthenticated.
    """
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not raw_token:
        return None

    session_row, user = get_session_and_user_by_token(db, raw_token)
    return user


def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """Enforces that the request is made by an authenticated user."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def get_current_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Enforces that the authenticated user possesses administrator privileges."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return user


def get_anonymous_id(
    request: Request,
    response: Response,
) -> str:
    """Extracts or issues the anonymous browser cookie."""
    return get_or_create_anonymous_id(request, response, secure=settings.cookie_secure)


def verify_csrf(
    request: Request,
) -> None:
    """Enforces CSRF token and Origin matching for mutating operations."""
    validate_csrf(request)
