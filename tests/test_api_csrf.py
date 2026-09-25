"""Unit tests for CSRF validation and Origin verification."""
import pytest
from fastapi import Request, HTTPException
from starlette.datastructures import Headers

from apps.api.auth.csrf import validate_csrf, generate_csrf_token


def make_request(
    method: str = "POST",
    headers: dict = None,
    cookies: dict = None,
) -> Request:
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    
    scope = {
        "type": "http",
        "method": method,
        "headers": raw_headers,
        "path": "/runs",
        "query_string": b"",
    }
    req = Request(scope)
    if cookies:
        req._cookies = cookies
    else:
        req._cookies = {}
    return req


def test_safe_method_exempt():
    req = make_request(method="GET")
    # Safe methods do not raise
    validate_csrf(req)


def test_missing_csrf_token_on_cookie_auth():
    req = make_request(
        method="POST",
        headers={"origin": "http://localhost:5173"},
        cookies={"blog_session": "active_session_token"},
    )
    with pytest.raises(HTTPException) as exc_info:
        validate_csrf(req)
    assert exc_info.value.status_code == 403
    assert "Missing CSRF token" in exc_info.value.detail


def test_csrf_token_mismatch():
    req = make_request(
        method="POST",
        headers={
            "origin": "http://localhost:5173",
            "x-csrf-token": "token_header_value",
        },
        cookies={
            "blog_session": "active_session_token",
            "blog_csrf": "token_cookie_mismatch",
        },
    )
    with pytest.raises(HTTPException) as exc_info:
        validate_csrf(req)
    assert exc_info.value.status_code == 403
    assert "CSRF token mismatch" in exc_info.value.detail


def test_csrf_token_match_success():
    token = generate_csrf_token()
    req = make_request(
        method="POST",
        headers={
            "origin": "http://localhost:5173",
            "x-csrf-token": token,
        },
        cookies={
            "blog_session": "active_session_token",
            "blog_csrf": token,
        },
    )
    # Valid CSRF does not raise
    validate_csrf(req)


def test_origin_disallowed():
    token = generate_csrf_token()
    req = make_request(
        method="POST",
        headers={
            "origin": "http://evil-attacker.com",
            "x-csrf-token": token,
        },
        cookies={
            "blog_session": "active_session_token",
            "blog_csrf": token,
        },
    )
    with pytest.raises(HTTPException) as exc_info:
        validate_csrf(req)
    assert exc_info.value.status_code == 403
    assert "Origin not allowed" in exc_info.value.detail
