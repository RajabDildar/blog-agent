"""Google Identity Services ID token verification."""
from typing import Optional
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from apps.api.schemas.auth import GoogleIdPayload


class GoogleAuthError(Exception):
    """Raised when Google ID token validation fails."""
    pass


ALLOWED_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_google_credential(
    credential: str,
    client_id: str,
    request_adapter: Optional[google_requests.Request] = None,
) -> GoogleIdPayload:
    """
    Verifies a Google ID token JWT using Google's public certs.
    Validates signature, audience (client_id), issuer, and expiration.
    """
    if not credential:
        raise GoogleAuthError("Missing Google credential")

    if request_adapter is None:
        request_adapter = google_requests.Request()

    try:
        id_info = id_token.verify_oauth2_token(
            credential,
            request_adapter,
            audience=client_id,
        )
    except Exception as e:
        raise GoogleAuthError(f"Invalid Google ID token: {str(e)}") from e

    issuer = id_info.get("iss")
    if issuer not in ALLOWED_ISSUERS:
        raise GoogleAuthError(f"Invalid token issuer: {issuer}")

    sub = id_info.get("sub")
    if not sub:
        raise GoogleAuthError("Token payload missing 'sub' identifier")

    email = id_info.get("email")
    if not email:
        raise GoogleAuthError("Token payload missing 'email'")

    return GoogleIdPayload(
        google_sub=str(sub),
        email=str(email),
        display_name=id_info.get("name"),
        avatar_url=id_info.get("picture"),
    )
