"""Phase 4 tests: HITL API endpoints (POST /runs/{id}/input, POST /runs/{id}/resume)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.config import get_settings
from apps.api.db.models import Run, RunStatus, User

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


@pytest.fixture(autouse=True)
def bypass_abuse_limit():
    with patch("apps.api.routers.runs.check_and_increment_abuse_limit"):
        yield


@pytest.fixture(scope="module")
def client():
    return TestClient(app, base_url="http://localhost:8000")


def _csrf_headers(client):
    token = "hitl-test-csrf-" + uuid.uuid4().hex[:8]
    client.cookies.set("blog_csrf", token)
    return {"origin": "http://localhost:5173", "x-csrf-token": token}


def _make_awaiting_input_run(db, interaction_type="needs_clarification"):
    """Helper to create an awaiting_input run with given pending_interaction type."""
    anon_id = "anon-hitl-" + uuid.uuid4().hex[:8]
    pending = {
        "type": interaction_type,
        "question": "What aspect of AI?",
        "options": ["Machine learning", "Deep learning", "Reinforcement learning"],
    }
    if interaction_type == "proposed_topic_confirmation":
        pending = {
            "type": "proposed_topic_confirmation",
            "proposed_topic": "Introduction to Machine Learning",
            "message": "We'll generate an article about this topic.",
        }
    run = Run(
        original_input="AI" if interaction_type == "needs_clarification" else "vague ai stuff",
        status=RunStatus.AWAITING_INPUT.value,
        anonymous_session_id=anon_id,
        pending_interaction=pending,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run, anon_id


# --- Clarification tests ---

def test_submit_clarification_select_option_valid(db, client):
    """Valid select_option from offered options should be accepted and enqueue resume."""
    run, anon_id = _make_awaiting_input_run(db, "needs_clarification")
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        res = client.post(
            f"/runs/{run.id}/input",
            json={"action": "select_option", "value": "Machine learning"},
            headers=headers,
        )

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "queued"
    assert data["pending_interaction"] is None


def test_submit_clarification_custom_input(db, client):
    """Custom text input should be accepted and enqueue resume."""
    run, anon_id = _make_awaiting_input_run(db, "needs_clarification")
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        res = client.post(
            f"/runs/{run.id}/input",
            json={"action": "custom_input", "value": "AI applications in precision medicine"},
            headers=headers,
        )

    assert res.status_code == 200
    assert res.json()["status"] == "queued"


def test_submit_clarification_wrong_option_rejected(db, client):
    """Selecting a non-offered option must return 400."""
    run, anon_id = _make_awaiting_input_run(db, "needs_clarification")
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        res = client.post(
            f"/runs/{run.id}/input",
            json={"action": "select_option", "value": "Quantum computing"},  # Not an offered option
            headers=headers,
        )

    assert res.status_code == 400
    assert "does not match" in res.json()["detail"].lower() or "does not match" in res.json()["detail"]


def test_submit_clarification_invalid_action_rejected(db, client):
    """Using 'proceed' action for a clarification interrupt must return 400."""
    run, anon_id = _make_awaiting_input_run(db, "needs_clarification")
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        res = client.post(
            f"/runs/{run.id}/input",
            json={"action": "proceed"},  # Wrong for clarification
            headers=headers,
        )

    assert res.status_code == 400


def test_submit_clarification_duplicate_rejected(db, client):
    """Second submission after pending_interaction is cleared should return 400."""
    run, anon_id = _make_awaiting_input_run(db, "needs_clarification")
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        # First submission clears pending_interaction
        first = client.post(
            f"/runs/{run.id}/input",
            json={"action": "select_option", "value": "Machine learning"},
            headers=headers,
        )
        assert first.status_code == 200

        # Second submission should fail because run is no longer awaiting_input
        second = client.post(
            f"/runs/{run.id}/input",
            json={"action": "select_option", "value": "Machine learning"},
            headers=headers,
        )

    assert second.status_code == 400


# --- Confirmation tests ---

def test_submit_confirmation_proceed(db, client):
    """'proceed' action on a confirmation interrupt should be accepted."""
    run, anon_id = _make_awaiting_input_run(db, "proposed_topic_confirmation")
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        res = client.post(
            f"/runs/{run.id}/input",
            json={"action": "proceed"},
            headers=headers,
        )

    assert res.status_code == 200
    assert res.json()["status"] == "queued"


def test_submit_confirmation_cancel(db, client):
    """'cancel' action on a confirmation interrupt should be accepted."""
    run, anon_id = _make_awaiting_input_run(db, "proposed_topic_confirmation")
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        res = client.post(
            f"/runs/{run.id}/input",
            json={"action": "cancel"},
            headers=headers,
        )

    assert res.status_code == 200


def test_submit_input_wrong_owner_forbidden(db, client):
    """Anonymous session with wrong anon_id must receive 403."""
    run, _ = _make_awaiting_input_run(db, "needs_clarification")
    client.cookies.set("blog_anon", "wrong-anon-id-9999")
    headers = _csrf_headers(client)

    res = client.post(
        f"/runs/{run.id}/input",
        json={"action": "select_option", "value": "Machine learning"},
        headers=headers,
    )

    assert res.status_code == 403


def test_submit_input_unknown_run_404(db, client):
    """Submitting input for non-existent run returns 404."""
    client.cookies.set("blog_anon", "some-anon-id")
    headers = _csrf_headers(client)

    res = client.post(
        f"/runs/{uuid.uuid4()}/input",
        json={"action": "select_option", "value": "Something"},
        headers=headers,
    )

    assert res.status_code == 404


# --- Resume paused/failed tests ---

def _make_paused_run(db, *, anon_id: str, resume_after: datetime | None = None):
    run = Run(
        original_input="Paused run topic",
        status=RunStatus.PAUSED.value,
        anonymous_session_id=anon_id,
        resume_after=resume_after,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def test_resume_paused_run_after_timer_succeeds(db, client):
    """Resume paused run when resume_after is in the past should succeed."""
    anon_id = "anon-resume-" + uuid.uuid4().hex[:8]
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    run = _make_paused_run(db, anon_id=anon_id, resume_after=past_time)
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        res = client.post(f"/runs/{run.id}/resume", headers=headers)

    assert res.status_code == 200
    assert res.json()["status"] == "queued"


def test_resume_paused_run_before_timer_rejected(db, client):
    """Resume paused run when resume_after is still in the future must return 400."""
    anon_id = "anon-resume-early-" + uuid.uuid4().hex[:8]
    future_time = datetime.now(timezone.utc) + timedelta(minutes=60)
    run = _make_paused_run(db, anon_id=anon_id, resume_after=future_time)
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    res = client.post(f"/runs/{run.id}/resume", headers=headers)

    assert res.status_code == 400
    assert "backoff" in res.json()["detail"].lower() or "wait" in res.json()["detail"].lower()


def test_resume_failed_run_succeeds(db, client):
    """Resume failed run (no time restriction) should succeed."""
    anon_id = "anon-failed-resume-" + uuid.uuid4().hex[:8]
    run = Run(
        original_input="Failed generation topic",
        status=RunStatus.FAILED.value,
        anonymous_session_id=anon_id,
        error_code="generation_failed",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        res = client.post(f"/runs/{run.id}/resume", headers=headers)

    assert res.status_code == 200
    assert res.json()["status"] == "queued"


def test_resume_completed_run_rejected(db, client):
    """Cannot resume a completed run - must return 400."""
    anon_id = "anon-completed-" + uuid.uuid4().hex[:8]
    run = Run(
        original_input="Completed topic",
        status=RunStatus.COMPLETED.value,
        anonymous_session_id=anon_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    client.cookies.set("blog_anon", anon_id)
    headers = _csrf_headers(client)

    res = client.post(f"/runs/{run.id}/resume", headers=headers)

    assert res.status_code == 400


def test_resume_wrong_owner_forbidden(db, client):
    """Resume with wrong anonymous session ID must be forbidden."""
    anon_id = "anon-resume-owner-" + uuid.uuid4().hex[:8]
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    run = _make_paused_run(db, anon_id=anon_id, resume_after=past_time)
    client.cookies.set("blog_anon", "different-anon-id")
    headers = _csrf_headers(client)

    res = client.post(f"/runs/{run.id}/resume", headers=headers)

    assert res.status_code == 403
