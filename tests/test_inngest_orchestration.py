"""Phase 4 tests: Inngest orchestration, event emission, execution functions, and outcome mapping."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.config import get_settings
from apps.api.db.models import Run, RunEvent, RunStatus

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


def _new_csrf(client):
    """Set and return a fresh CSRF token pair on the client."""
    token = "inngest-test-csrf-" + uuid.uuid4().hex[:8]
    client.cookies.set("blog_csrf", token)
    return {"origin": "http://localhost:5173", "x-csrf-token": token}


# ---------------------------------------------------------------------------
# Inngest event dispatching tests (via POST /runs)
# ---------------------------------------------------------------------------


def test_post_runs_emits_inngest_start_event(db):
    """POST /runs must emit 'blog-agent/run.start' event with the new run's ID."""
    from apps.api.main import app

    client = TestClient(app, base_url="http://localhost:8000")
    headers = _new_csrf(client)
    dispatched_events = []

    def mock_send(name, data):
        dispatched_events.append({"name": name, "data": data})
        return ["mock-event-id"]

    with (
        patch("apps.api.routers.runs.send_inngest_event", side_effect=mock_send),
        patch("apps.api.routers.runs.check_and_increment_abuse_limit"),
        patch("apps.api.routers.runs.check_pre_generation_quota"),
    ):
        res = client.post(
            "/runs",
            json={"input": "Test topic for Inngest event"},
            headers=headers,
        )

    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "queued"
    run_id = data["id"]

    assert len(dispatched_events) == 1
    assert dispatched_events[0]["name"] == "blog-agent/run.start"
    assert dispatched_events[0]["data"]["run_id"] == run_id


def test_post_runs_does_not_invoke_graph_inline(db):
    """POST /runs must never call the LangGraph agent synchronously."""
    from apps.api.main import app

    client = TestClient(app, base_url="http://localhost:8000")
    headers = _new_csrf(client)

    with (
        patch("apps.api.routers.runs.send_inngest_event"),
        patch("apps.api.routers.runs.check_and_increment_abuse_limit"),
        patch("apps.api.routers.runs.check_pre_generation_quota"),
        patch("blog_agent.run") as mock_agent_run,
    ):
        res = client.post(
            "/runs",
            json={"input": "Graph inline safety check"},
            headers=headers,
        )
    assert res.status_code == 202
    mock_agent_run.assert_not_called()


def test_post_runs_persists_queued_event(db):
    """POST /runs must insert a 'run_queued' event in run_events table."""
    from apps.api.main import app

    client = TestClient(app, base_url="http://localhost:8000")
    headers = _new_csrf(client)

    with (
        patch("apps.api.routers.runs.send_inngest_event"),
        patch("apps.api.routers.runs.check_and_increment_abuse_limit"),
        patch("apps.api.routers.runs.check_pre_generation_quota"),
    ):
        res = client.post(
            "/runs",
            json={"input": "Test initial event for Inngest"},
            headers=headers,
        )

    assert res.status_code == 202
    run_id = res.json()["id"]

    events = db.query(RunEvent).filter(RunEvent.run_id == run_id).all()
    assert len(events) == 1
    assert events[0].event_type == "run_queued"
    assert events[0].sequence == 1


# ---------------------------------------------------------------------------
# Inngest Serve Endpoint discovery test
# ---------------------------------------------------------------------------


def test_inngest_serve_endpoint_returns_schema():
    """GET /api/inngest must return 200 with registered function metadata."""
    from apps.api.main import app

    client = TestClient(app, base_url="http://localhost:8000")

    res = client.get("/api/inngest")
    assert res.status_code == 200
    data = res.json()
    assert "function_count" in data
    assert data["function_count"] >= 3  # start_run, resume_run, cleanup_expired_runs


# ---------------------------------------------------------------------------
# Inngest Execution Function unit tests
# ---------------------------------------------------------------------------


def test_execute_start_run_passes_original_input_to_agent(db):
    """execute_start_run() must pass original_input from DB to the agent as first argument."""
    from apps.api.inngest.functions import execute_start_run

    run = Run(
        original_input="Test inngest job original input",
        status=RunStatus.QUEUED.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    with (
        patch("apps.api.inngest.functions.agent_run") as mock_run,
        patch("apps.api.inngest.functions.create_checkpointer") as mock_cp,
        patch("apps.api.inngest.functions._handle_run_outcome"),
    ):
        mock_handle = MagicMock()
        mock_handle.close = MagicMock()
        mock_cp.return_value = mock_handle
        res = execute_start_run(run_id)

    assert res["status"] == "completed"
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert call_args[0][0] == "Test inngest job original input"
    assert call_args[1]["run_id"] == run_id


def test_execute_start_run_skips_non_queued_run(db):
    """execute_start_run() must skip execution if run is in terminal status."""
    from apps.api.inngest.functions import execute_start_run

    run = Run(
        original_input="Already done topic",
        status=RunStatus.COMPLETED.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    with (
        patch("apps.api.inngest.functions.agent_run") as mock_run,
        patch("apps.api.inngest.functions.create_checkpointer"),
    ):
        res = execute_start_run(run_id)

    assert res["status"] == "skipped"
    mock_run.assert_not_called()


def test_execute_resume_run_calls_agent_resume(db):
    """execute_resume_run() must call agent_resume with the run_id and human_response."""
    from apps.api.inngest.functions import execute_resume_run

    run = Run(
        original_input="Topic needing clarification",
        status=RunStatus.AWAITING_INPUT.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    human_response = {
        "action": "select_option",
        "value": "Machine learning in healthcare",
    }

    with (
        patch("apps.api.inngest.functions.agent_resume") as mock_resume,
        patch("apps.api.inngest.functions.create_checkpointer") as mock_cp,
        patch("apps.api.inngest.functions._handle_run_outcome"),
    ):
        mock_handle = MagicMock()
        mock_handle.close = MagicMock()
        mock_cp.return_value = mock_handle
        res = execute_resume_run(run_id, human_response)

    assert res["status"] == "completed"
    mock_resume.assert_called_once()
    call_kwargs = mock_resume.call_args[1]
    assert call_kwargs["run_id"] == run_id


def test_start_run_maps_blocked_outcome(db):
    """Function must set status='blocked' and error_code='input_blocked' for blocked result."""
    from apps.api.inngest.functions import execute_start_run

    run = Run(
        original_input="Violates policy",
        status=RunStatus.QUEUED.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    blocked_result = {
        "intent_status": "blocked",
        "intent_message": "This request violates content policy.",
    }

    with (
        patch("apps.api.inngest.functions.agent_run", return_value=blocked_result),
        patch("apps.api.inngest.functions.create_checkpointer") as mock_cp,
        patch("apps.api.inngest.functions._get_interrupt_payload", return_value=None),
    ):
        mock_handle = MagicMock()
        mock_handle.close = MagicMock()
        mock_cp.return_value = mock_handle
        execute_start_run(run_id)

    db.expire_all()
    fresh_run = db.get(Run, run_id)
    assert fresh_run is not None
    assert fresh_run.status == RunStatus.BLOCKED.value
    assert fresh_run.error_code == "input_blocked"
    assert fresh_run.generation_started_at is None


def test_start_run_maps_invalid_outcome(db):
    """Function must set status='invalid' and error_code='invalid_input' for invalid result."""
    from apps.api.inngest.functions import execute_start_run

    run = Run(
        original_input="Tell me a joke",
        status=RunStatus.QUEUED.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    invalid_result = {
        "intent_status": "invalid",
        "intent_message": "Jokes are out of scope.",
    }

    with (
        patch("apps.api.inngest.functions.agent_run", return_value=invalid_result),
        patch("apps.api.inngest.functions.create_checkpointer") as mock_cp,
        patch("apps.api.inngest.functions._get_interrupt_payload", return_value=None),
    ):
        mock_handle = MagicMock()
        mock_handle.close = MagicMock()
        mock_cp.return_value = mock_handle
        execute_start_run(run_id)

    db.expire_all()
    fresh_run = db.get(Run, run_id)
    assert fresh_run is not None
    assert fresh_run.status == RunStatus.INVALID.value
    assert fresh_run.error_code == "invalid_input"
    assert fresh_run.generation_started_at is None


def test_start_run_maps_interrupt_to_awaiting_input(db):
    """Function must set status='awaiting_input' and persist pending_interaction when interrupted."""
    from apps.api.inngest.functions import execute_start_run

    run = Run(
        original_input="Cloud computing",
        status=RunStatus.QUEUED.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    interrupt_payload = {
        "type": "clarification_required",
        "question": "What aspect of cloud computing?",
        "options": ["Serverless", "Kubernetes", "Cost optimization"],
    }

    with (
        patch("apps.api.inngest.functions.agent_run", return_value={}),
        patch("apps.api.inngest.functions.create_checkpointer") as mock_cp,
        patch(
            "apps.api.inngest.functions._get_interrupt_payload",
            return_value=interrupt_payload,
        ),
    ):
        mock_handle = MagicMock()
        mock_handle.close = MagicMock()
        mock_cp.return_value = mock_handle
        execute_start_run(run_id)

    db.expire_all()
    fresh_run = db.get(Run, run_id)
    assert fresh_run is not None
    assert fresh_run.status == RunStatus.AWAITING_INPUT.value
    assert fresh_run.pending_interaction == interrupt_payload


def test_handle_run_failure_sets_failed_status(db):
    """_handle_run_failure must mark run as FAILED with error_code='generation_failed'."""
    from apps.api.inngest.functions import _handle_run_failure

    run = Run(
        original_input="Failure test topic",
        status=RunStatus.RUNNING.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    _handle_run_failure(run_id, RuntimeError("Something went wrong"))

    db.expire_all()
    fresh = db.get(Run, run_id)
    assert fresh.status == RunStatus.FAILED.value
    assert fresh.error_code == "generation_failed"


def test_inngest_send_failure_returns_503(db):
    """When send_inngest_event fails, POST /runs, /input, and /resume must return 503 and preserve state."""
    from apps.api.main import app

    client = TestClient(app, base_url="http://localhost:8000")
    headers = _new_csrf(client)

    # 1. POST /runs failure
    with (
        patch("apps.api.routers.runs.check_and_increment_abuse_limit"),
        patch("apps.api.routers.runs.check_pre_generation_quota"),
        patch(
            "apps.api.routers.runs.send_inngest_event",
            side_effect=RuntimeError("Inngest down"),
        ),
    ):
        res = client.post(
            "/runs",
            json={"input": "Inngest failure check"},
            headers=headers,
        )
    assert res.status_code == 503
    err = res.json()["error"]
    assert err["code"] == "service_unavailable"
    assert "Inngest down" in err["message"]
    # Check that the run was created and marked failed in DB
    failed_run = db.query(Run).filter(Run.id == err["run_id"]).first()
    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.error_code == "send_failure"

    # 2. POST /runs/{id}/input failure restores awaiting_input & pending_interaction
    run = Run(
        id=str(uuid.uuid4()),
        anonymous_session_id="anon-failure-test",
        original_input="Topic",
        status=RunStatus.AWAITING_INPUT.value,
        pending_interaction={
            "type": "clarification_required",
            "options": ["Option A", "Option B"],
        },
    )
    db.add(run)
    db.commit()

    client.cookies.set("blog_anon", "anon-failure-test")
    with patch(
        "apps.api.routers.runs.send_inngest_event",
        side_effect=RuntimeError("Inngest network error"),
    ):
        res_input = client.post(
            f"/runs/{run.id}/input",
            json={"action": "select_option", "value": "Option A"},
            headers=headers,
        )
    assert res_input.status_code == 503
    db.refresh(run)
    assert run.status == RunStatus.AWAITING_INPUT.value
    assert run.pending_interaction is not None
    assert run.pending_interaction["options"] == ["Option A", "Option B"]

    # 3. POST /runs/{id}/resume failure restores paused/failed status
    run.status = RunStatus.PAUSED.value
    run.pending_interaction = None
    db.commit()

    with patch(
        "apps.api.routers.runs.send_inngest_event",
        side_effect=RuntimeError("Inngest timeout"),
    ):
        res_resume = client.post(
            f"/runs/{run.id}/resume",
            headers=headers,
        )
    assert res_resume.status_code == 503
    db.refresh(run)
    assert run.status == RunStatus.PAUSED.value


def test_error_envelope_shape():
    """All JSON error responses must adhere to {'error': {'code', 'message', 'run_id'}}."""
    from apps.api.main import app

    client = TestClient(app, base_url="http://localhost:8000")

    # 404 error
    res_404 = client.get(f"/runs/{uuid.uuid4()}")
    assert res_404.status_code == 404
    body = res_404.json()
    assert "error" in body
    assert isinstance(body["error"], dict)
    assert "code" in body["error"]
    assert "message" in body["error"]
    assert "run_id" in body["error"]
    assert body["error"]["code"] == "run_not_found"

    # 422 error
    res_422 = client.get("/gallery?page_size=-1")
    assert res_422.status_code == 422
    body_422 = res_422.json()
    assert "error" in body_422
    assert body_422["error"]["code"] == "validation_error"
