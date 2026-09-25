"""Authentication router providing Google login, session cookies, and logout."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import get_db, get_current_user, verify_csrf
from apps.api.db.models import User
from apps.api.schemas.auth import GoogleAuthRequest, UserResponse
from apps.api.auth.google import verify_google_credential, GoogleAuthError
from apps.api.auth.sessions import (
    create_session,
    revoke_session,
    set_session_cookie,
    clear_session_cookie,
)
from apps.api.auth.csrf import generate_csrf_token, set_csrf_cookie, clear_csrf_cookie
from apps.api.services.claim_service import claim_anonymous_runs

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/google", response_model=UserResponse)
def login_with_google(
    payload: GoogleAuthRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Authenticates a user via Google Identity Services ID token.
    Creates or retrieves the user record by Google `sub`.
    Claims any unowned runs matching the visitor's anonymous cookie.
    Issues opaque session cookie and CSRF cookie.
    """
    try:
        id_info = verify_google_credential(
            credential=payload.credential,
            client_id=settings.GOOGLE_CLIENT_ID,
        )
    except GoogleAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    # Lookup or create user by google_sub
    stmt = select(User).where(User.google_sub == id_info.google_sub)
    user = db.scalar(stmt)
    if not user:
        user = User(
            google_sub=id_info.google_sub,
            email=id_info.email,
            display_name=id_info.display_name,
            avatar_url=id_info.avatar_url,
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update profile attributes if changed
        updated = False
        if id_info.display_name and user.display_name != id_info.display_name:
            user.display_name = id_info.display_name
            updated = True
        if id_info.avatar_url and user.avatar_url != id_info.avatar_url:
            user.avatar_url = id_info.avatar_url
            updated = True
        if updated:
            db.commit()
            db.refresh(user)

    # Claim anonymous runs if anonymous cookie is present
    anon_cookie = request.cookies.get(settings.ANONYMOUS_COOKIE_NAME)
    if anon_cookie:
        claim_anonymous_runs(db, anonymous_session_id=anon_cookie, user_id=user.id)

    # Create opaque session
    session_row, raw_token = create_session(db, user_id=user.id)
    set_session_cookie(response, raw_token)

    # Rotate/issue CSRF cookie
    csrf_token = generate_csrf_token()
    set_csrf_cookie(response, csrf_token)

    return user


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _csrf: None = Depends(verify_csrf),
):
    """
    Terminates the active session and clears authentication and CSRF cookies.
    """
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if raw_token:
        revoke_session(db, raw_token)

    clear_session_cookie(response)
    clear_csrf_cookie(response)
    return {"detail": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """Returns the authenticated user's profile details."""
    return current_user
