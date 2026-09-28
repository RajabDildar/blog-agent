"""End-to-end API integration tests for FastAPI routes, cookies, and authorization."""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.main import app
from apps.api.config import get_settings
from apps.api.db.models import User, Run, RunStatus, RunVisibility
from apps.api.services.run_service import create_run
from apps.api.auth.csrf import generate_csrf_token

settings = get_settings()

@pytest.fixture(autouse=True)
def bypass_abuse_limit():
    with patch("apps.api.routers.runs.check_and_increment_abuse_limit"):
        yield


@pytest.fixture(scope="module")
def client():
    return TestClient(app, base_url="http://localhost:8000")

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


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_google_login_and_logout_flow(client):
    google_sub = f"sub-{uuid.uuid4().hex}"
    email = f"user_{uuid.uuid4().hex[:6]}@example.com"
    mock_payload = {
        "iss": "https://accounts.google.com",
        "sub": google_sub,
        "email": email,
        "name": "E2E User",
        "picture": "https://example.com/pic.jpg",
    }

    # 1. Login with Google
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_payload):
        res = client.post("/auth/google", json={"credential": "mock.jwt.token"})
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == email
        assert data["display_name"] == "E2E User"
        assert not data["is_admin"]

        # Verify cookies
        assert settings.SESSION_COOKIE_NAME in res.cookies
        assert settings.CSRF_COOKIE_NAME in res.cookies
        csrf_token = res.cookies[settings.CSRF_COOKIE_NAME]

    # 2. Get current user profile (/auth/me)
    me_res = client.get("/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email

    # 3. Logout without CSRF fails
    bad_logout = client.post("/auth/logout")
    assert bad_logout.status_code == 403

    # 4. Logout with valid CSRF succeeds
    logout_res = client.post(
        "/auth/logout",
        headers={
            "origin": "http://localhost:5173",
            "x-csrf-token": csrf_token,
        },
    )
    assert logout_res.status_code == 200

    # 5. After logout, /auth/me returns 401
    me_after = client.get("/auth/me")
    assert me_after.status_code == 401


def test_anonymous_run_creation_and_claim_on_login(client, db):
    # Use a separate test client for anonymous flow
    anon_client = TestClient(app, base_url="http://localhost:8000")

    # 1. Anonymous visitor submits a run
    res = anon_client.post(
        "/runs",
        json={"input": "Distributed consensus in modern cloud systems"},
    )
    assert res.status_code == 201
    run_data = res.json()
    assert run_data["status"] == "queued"
    assert run_data["visibility"] == "private"
    assert run_data["original_input"] == "Distributed consensus in modern cloud systems"
    run_id = run_data["id"]

    # Verify anonymous cookie is set
    assert settings.ANONYMOUS_COOKIE_NAME in res.cookies
    anon_cookie = res.cookies[settings.ANONYMOUS_COOKIE_NAME]

    # 2. Anonymous visitor can read own run
    get_res = anon_client.get(f"/runs/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == run_id

    # 3. Different client cannot read this anonymous run
    other_client = TestClient(app, base_url="http://localhost:8000")
    forbidden_get = other_client.get(f"/runs/{run_id}")
    assert forbidden_get.status_code == 404

    # 4. Anonymous visitor now logs in via Google
    google_sub = f"sub-{uuid.uuid4().hex}"
    email = f"claim_{uuid.uuid4().hex[:6]}@example.com"
    mock_payload = {
        "iss": "https://accounts.google.com",
        "sub": google_sub,
        "email": email,
        "name": "Claiming User",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_payload):
        login_res = anon_client.post("/auth/google", json={"credential": "mock.jwt.token"})
        assert login_res.status_code == 200
        user_id = login_res.json()["id"]

    # 5. Verify the run was claimed by this user
    run_row = db.query(Run).filter(Run.id == run_id).first()
    assert run_row.user_id == user_id
    assert run_row.anonymous_session_id is None

    # 6. User can still read their run
    claimed_get = anon_client.get(f"/runs/{run_id}")
    assert claimed_get.status_code == 200
    assert claimed_get.json()["id"] == run_id


def test_visibility_and_feature_endpoints(client, db):
    # Create an admin user directly in DB
    admin = User(
        google_sub=f"sub-admin-{uuid.uuid4().hex}",
        email="admin@example.com",
        display_name="Admin User",
        is_admin=True,
    )
    # Create a regular user
    regular = User(
        google_sub=f"sub-reg-{uuid.uuid4().hex}",
        email="reg@example.com",
        display_name="Regular User",
        is_admin=False,
    )
    db.add_all([admin, regular])
    db.commit()

    # Regular user creates run
    run = create_run(db, original_input="Kubernetes networking", user_id=regular.id)
    run_id = run.id

    # Login as regular user
    mock_reg = {
        "iss": "https://accounts.google.com",
        "sub": regular.google_sub,
        "email": regular.email,
    }
    reg_client = TestClient(app, base_url="http://localhost:8000")
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_reg):
        reg_login = reg_client.post("/auth/google", json={"credential": "reg.token"})
        csrf_reg = reg_login.cookies[settings.CSRF_COOKIE_NAME]

    # Incomplete run cannot be made public
    bad_vis = reg_client.patch(
        f"/runs/{run_id}/visibility",
        json={"visibility": "public"},
        headers={"origin": "http://localhost:5173", "x-csrf-token": csrf_reg},
    )
    assert bad_vis.status_code == 400
    assert "Only completed runs can be made public" in bad_vis.json()["detail"]

    # Mark run completed
    run.status = RunStatus.COMPLETED.value
    run.completed_at = datetime.now(timezone.utc)
    db.commit()

    # Regular user makes completed run public
    good_vis = reg_client.patch(
        f"/runs/{run_id}/visibility",
        json={"visibility": "public"},
        headers={"origin": "http://localhost:5173", "x-csrf-token": csrf_reg},
    )
    assert good_vis.status_code == 200
    assert good_vis.json()["visibility"] == "public"

    # Regular user tries to feature -> 403 Forbidden
    non_admin_feat = reg_client.patch(
        f"/runs/{run_id}/feature",
        json={"featured": True},
        headers={"origin": "http://localhost:5173", "x-csrf-token": csrf_reg},
    )
    assert non_admin_feat.status_code == 403

    # Login as admin
    mock_admin = {
        "iss": "https://accounts.google.com",
        "sub": admin.google_sub,
        "email": admin.email,
    }
    admin_client = TestClient(app, base_url="http://localhost:8000")
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_admin):
        admin_login = admin_client.post("/auth/google", json={"credential": "admin.token"})
        csrf_admin = admin_login.cookies[settings.CSRF_COOKIE_NAME]

    # Admin features the public completed run
    admin_feat = admin_client.patch(
        f"/runs/{run_id}/feature",
        json={"featured": True},
        headers={"origin": "http://localhost:5173", "x-csrf-token": csrf_admin},
    )
    assert admin_feat.status_code == 200
    assert admin_feat.json()["featured"] is True

    # Public gallery and featured endpoints return the article
    gallery_res = client.get("/gallery")
    assert gallery_res.status_code == 200
    assert any(a["id"] == run_id for a in gallery_res.json())

    featured_res = client.get("/featured")
    assert featured_res.status_code == 200
    assert any(a["id"] == run_id for a in featured_res.json())


def test_phase_4_endpoints_not_found_on_unknown_run(client):
    run_id = str(uuid.uuid4())
    csrf_token = "test-csrf-token-12345"
    client.cookies.set("blog_csrf", csrf_token)
    headers = {
        "origin": "http://localhost:5173",
        "x-csrf-token": csrf_token,
    }

    res_input = client.post(
        f"/runs/{run_id}/input",
        json={"action": "select_option", "value": "Option 1"},
        headers=headers,
    )
    assert res_input.status_code == 404

    res_resume = client.post(f"/runs/{run_id}/resume", headers=headers)
    assert res_resume.status_code == 404

    res_events = client.get(f"/runs/{run_id}/events")
    assert res_events.status_code == 404


def test_public_read_does_not_expose_owner_fields(db, client):
    """Public read of stranger's run must only return PublicRunResponse fields."""
    user = User(
        google_sub=f"sub-{uuid.uuid4().hex}",
        email=f"owner_{uuid.uuid4().hex[:6]}@example.com",
        display_name="Owner User",
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    owner_id = user.id
    run = Run(
        id=str(uuid.uuid4()),
        user_id=owner_id,
        original_input="Secret confidential input",
        topic="Architecture of LLMs",
        status=RunStatus.COMPLETED.value,
        visibility=RunVisibility.PUBLIC.value,
        featured=False,
        article_title="Architecture of LLMs",
        article_excerpt="Deep dive into transformers",
        diagnostics_summary={"latency_ms": 1200},
        error_message="Internal warning",
        article_assets=[{"filename": "diag.png"}],
        completed_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()

    # Stranger reads the public run
    stranger_res = client.get(f"/runs/{run.id}")
    assert stranger_res.status_code == 200
    data = stranger_res.json()

    # Public fields present
    assert data["id"] == run.id
    assert data["topic"] == "Architecture of LLMs"
    assert data["article_title"] == "Architecture of LLMs"
    assert data["article_excerpt"] == "Deep dive into transformers"
    assert data["article_url"] == f"/articles/{run.id}"
    assert data["status"] == "completed"
    assert data["visibility"] == "public"

    # Owner-only fields MUST NOT be exposed
    assert "original_input" not in data
    assert "user_id" not in data
    assert "diagnostics_summary" not in data
    assert "error_message" not in data
    assert "article_assets" not in data
    assert "run_url" not in data


def test_anonymous_cannot_publish(db, client):
    """Anonymous run owner cannot change visibility to public."""
    anon_id = f"anon-{uuid.uuid4()}"
    run = Run(
        id=str(uuid.uuid4()),
        anonymous_session_id=anon_id,
        user_id=None,
        original_input="Explain Rust borrow checker",
        topic="Rust Borrow Checker",
        status=RunStatus.COMPLETED.value,
        visibility=RunVisibility.PRIVATE.value,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()

    client.cookies.set(settings.ANONYMOUS_COOKIE_NAME, anon_id)
    csrf_token = "csrf-test-token"
    client.cookies.set(settings.CSRF_COOKIE_NAME, csrf_token)
    headers = {
        "origin": "http://localhost:5173",
        "x-csrf-token": csrf_token,
    }

    res = client.patch(
        f"/runs/{run.id}/visibility",
        json={"visibility": "public"},
        headers=headers,
    )
    assert res.status_code == 403
    assert "Anonymous runs cannot be made public" in res.json()["detail"]


def test_orphan_run_access_denied(db, client):
    """Orphan runs with no user_id and no anonymous_session_id reject all access."""
    run = Run(
        id=str(uuid.uuid4()),
        user_id=None,
        anonymous_session_id=None,
        original_input="Orphan input",
        status=RunStatus.AWAITING_INPUT.value,
        pending_interaction={"type": "clarification_required", "options": ["A", "B"]},
    )
    db.add(run)
    db.commit()

    csrf_token = "csrf-test-token"
    client.cookies.set(settings.CSRF_COOKIE_NAME, csrf_token)
    headers = {
        "origin": "http://localhost:5173",
        "x-csrf-token": csrf_token,
    }

    # Stranger or anyone attempting input
    res_input = client.post(
        f"/runs/{run.id}/input",
        json={"action": "select_option", "value": "A"},
        headers=headers,
    )
    assert res_input.status_code in (403, 404)

    # Stranger attempting resume
    run.status = RunStatus.FAILED.value
    db.commit()
    res_resume = client.post(f"/runs/{run.id}/resume", headers=headers)
    assert res_resume.status_code in (403, 404)

    # Stranger attempting SSE
    res_events = client.get(f"/runs/{run.id}/events")
    assert res_events.status_code in (403, 404)


