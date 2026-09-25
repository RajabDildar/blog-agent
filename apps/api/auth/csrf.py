"""Double-submit-cookie CSRF protection and Origin verification."""
import hmac
import secrets
from urllib.parse import urlparse
from typing import List, Optional
from fastapi import Request, Response, HTTPException, status
from apps.api.config import get_settings

settings = get_settings()

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def generate_csrf_token() -> str:
    """Generates a cryptographically random 32-byte hex CSRF token."""
    return secrets.token_hex(32)


def set_csrf_cookie(
    response: Response,
    token: str,
    secure: Optional[bool] = None,
) -> None:
    """
    Sets the non-HttpOnly CSRF cookie so the frontend SPA can read it
    and attach it to the `X-CSRF-Token` header.
    """
    if secure is None:
        secure = settings.cookie_secure

    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=False,  # Accessible to JavaScript for double-submit
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_csrf_cookie(response: Response) -> None:
    """Clears the CSRF cookie."""
    response.delete_cookie(
        key=settings.CSRF_COOKIE_NAME,
        path="/",
        samesite="lax",
    )


def validate_origin(request: Request, allowed_origins: List[str]) -> bool:
    """
    Validates request Origin against configured allowed origins.
    Returns True if origin is valid or permitted.
    """
    origin = request.headers.get("origin")
    if not origin:
        # Fallback to Referer host if Origin is omitted
        referer = request.headers.get("referer")
        if referer:
            parsed = urlparse(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}"

    if not origin:
        # No origin or referer header
        return True

    normalized_origin = origin.rstrip("/")
    normalized_allowed = {o.rstrip("/") for o in allowed_origins}
    return normalized_origin in normalized_allowed


def validate_csrf(request: Request) -> None:
    """
    Validates CSRF token and Origin for mutating HTTP requests.
    Exempts SAFE_METHODS (GET, HEAD, OPTIONS).
    Raises HTTPException(403) on violation.
    """
    if request.method.upper() in SAFE_METHODS:
        return

    # Verify origin
    allowed = (
        settings.ALLOWED_ORIGINS
        if isinstance(settings.ALLOWED_ORIGINS, list)
        else [settings.ALLOWED_ORIGINS]
    )
    if not validate_origin(request, allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Origin not allowed",
        )

    # If request is cookie-authenticated (i.e. has blog_session cookie),
    # CSRF check is strictly mandatory.
    has_session_cookie = settings.SESSION_COOKIE_NAME in request.cookies
    cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    header_token = request.headers.get("x-csrf-token")

    # If there's a CSRF cookie or a session cookie, enforce match
    if has_session_cookie or cookie_token:
        if not cookie_token or not header_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing CSRF token in cookie or X-CSRF-Token header",
            )

        if not hmac.compare_digest(cookie_token, header_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token mismatch",
            )
