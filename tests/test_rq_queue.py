"""Phase 4 tests: RQ queue integration, job enqueueing, and worker job behavior."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.db.models import Run, RunStatus, RunEvent

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


@pytest.fixture(scope="module")
def client():
    return TestClient(app, base_url="http://localhost:8000")


def _new_csrf(client):
    """Set and return a fresh CSRF token pair on the client."""
    token = "rq-test-csrf-" + uuid.uuid4().hex[:8]
    client.cookies.set("blog_csrf", token)
    return {"origin": "http://localhost:5173", "x-csrf-token": token}


# ---------------------------------------------------------------------------
# Queue enqueueing tests (via POST /runs)
# ---------------------------------------------------------------------------

def test_post_runs_enqueues_start_run_job(db):
    """POST /runs must enqueue 'start_run' job with the new run's ID."""
    from apps.api.main import app
    client = TestClient(app, base_url="http://localhost:8000")
    headers = _new_csrf(client)
    enqueued = []

    class FakeQueue:
        def enqueue(self, fn, *args, **kwargs):
            enqueued.append({"fn": fn, "args": args})

    with patch("apps.api.routers.runs.get_queue", return_value=FakeQueue()):
        with patch("apps.api.routers.runs.check_and_increment_abuse_limit"):
            with patch("apps.api.routers.runs.check_pre_generation_quota"):
                res = client.post(
                    "/runs",
                    json={"input": "Test topic for RQ enqueue"},
                    headers=headers,
                )

    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "queued"
    run_id = data["id"]

    assert len(enqueued) == 1
    assert "start_run" in enqueued[0]["fn"]
    assert enqueued[0]["args"][0] == run_id


def test_post_runs_does_not_invoke_graph_inline(db):
    """POST /runs must never call the LangGraph agent synchronously."""
    from apps.api.main import app
    client = TestClient(app, base_url="http://localhost:8000")
    headers = _new_csrf(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        with patch("apps.api.routers.runs.check_and_increment_abuse_limit"):
            with patch("apps.api.routers.runs.check_pre_generation_quota"):
                with patch("blog_agent.run") as mock_agent_run:
                    res = client.post(
                        "/runs",
                        json={"input": "Graph inline safety check"},
                        headers=headers,
                    )
    assert res.status_code == 201
    mock_agent_run.assert_not_called()


def test_post_runs_persists_queued_event(db):
    """POST /runs must insert a 'run_queued' event in run_events table."""
    from apps.api.main import app
    client = TestClient(app, base_url="http://localhost:8000")
    headers = _new_csrf(client)

    with patch("apps.api.routers.runs.get_queue", return_value=MagicMock()):
        with patch("apps.api.routers.runs.check_and_increment_abuse_limit"):
            with patch("apps.api.routers.runs.check_pre_generation_quota"):
                res = client.post(
                    "/runs",
                    json={"input": "Test initial event"},
                    headers=headers,
                )

    assert res.status_code == 201
    run_id = res.json()["id"]

    events = db.query(RunEvent).filter(RunEvent.run_id == run_id).all()
    assert len(events) == 1
    assert events[0].event_type == "run_queued"
    assert events[0].sequence == 1


# ---------------------------------------------------------------------------
# Worker job unit tests
# ---------------------------------------------------------------------------

def test_start_run_job_passes_original_input_to_agent(db):
    """start_run() must pass original_input from DB to the agent as the first argument."""
    from apps.api.workers.jobs import start_run

    run = Run(
        original_input="Test job original input",
        status=RunStatus.QUEUED.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    with patch("apps.api.workers.jobs.agent_run") as mock_run:
        with patch("apps.api.workers.jobs.create_checkpointer") as mock_cp:
            mock_handle = MagicMock()
            mock_handle.close = MagicMock()
            mock_cp.return_value = mock_handle
            with patch("apps.api.workers.jobs._handle_run_outcome"):
                start_run(run_id)

    mock_run.assert_called_once()
    call_args = mock_run.call_args
    # positional first arg should be the original_input
    assert call_args[0][0] == "Test job original input"
    # run_id must be passed as keyword arg
    assert call_args[1]["run_id"] == run_id


def test_start_run_job_skips_non_queued_run(db):
    """start_run() must skip execution if run is already in a non-queued status."""
    from apps.api.workers.jobs import start_run

    run = Run(
        original_input="Already done topic",
        status=RunStatus.COMPLETED.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    with patch("apps.api.workers.jobs.agent_run") as mock_run:
        with patch("apps.api.workers.jobs.create_checkpointer"):
            start_run(run_id)

    mock_run.assert_not_called()


def test_resume_run_job_calls_agent_resume(db):
    """resume_run() must call agent_resume with the run_id and human_response kwargs."""
    from apps.api.workers.jobs import resume_run

    run = Run(
        original_input="Topic needing clarification",
        status=RunStatus.AWAITING_INPUT.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    human_response = {"action": "select_option", "value": "Machine learning in healthcare"}

    with patch("apps.api.workers.jobs.agent_resume") as mock_resume:
        with patch("apps.api.workers.jobs.create_checkpointer") as mock_cp:
            mock_handle = MagicMock()
            mock_handle.close = MagicMock()
            mock_cp.return_value = mock_handle
            with patch("apps.api.workers.jobs._handle_run_outcome"):
                resume_run(run_id, human_response)

    mock_resume.assert_called_once()
    call_kwargs = mock_resume.call_args[1]
    assert call_kwargs["run_id"] == run_id


def test_start_run_maps_blocked_outcome(db):
    """Worker must set status='blocked' and error_code='input_blocked' for blocked result."""
    from apps.api.workers.jobs import start_run

    run = Run(
        original_input="How to make a bomb",
        status=RunStatus.QUEUED.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    blocked_result = {
        "intent_status": "blocked",
        "intent_message": "This request violates content policy.",
    }

    with patch("apps.api.workers.jobs.agent_run", return_value=blocked_result):
        with patch("apps.api.workers.jobs.create_checkpointer") as mock_cp:
            mock_handle = MagicMock()
            mock_handle.close = MagicMock()
            mock_cp.return_value = mock_handle
            with patch("apps.api.workers.jobs._get_interrupt_payload", return_value=None):
                start_run(run_id)

    # Use a fresh session to see committed state
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    verify_engine = create_engine(settings.DATABASE_URL)
    VerifySession = sessionmaker(bind=verify_engine)
    with VerifySession() as vsession:
        fresh_run = vsession.get(Run, run_id)
        assert fresh_run is not None
        assert fresh_run.status == RunStatus.BLOCKED.value
        assert fresh_run.error_code == "input_blocked"
        assert fresh_run.generation_started_at is None


def test_start_run_maps_invalid_outcome(db):
    """Worker must set status='invalid' and error_code='invalid_input' for invalid result."""
    from apps.api.workers.jobs import start_run

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

    with patch("apps.api.workers.jobs.agent_run", return_value=invalid_result):
        with patch("apps.api.workers.jobs.create_checkpointer") as mock_cp:
            mock_handle = MagicMock()
            mock_handle.close = MagicMock()
            mock_cp.return_value = mock_handle
            with patch("apps.api.workers.jobs._get_interrupt_payload", return_value=None):
                start_run(run_id)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    verify_engine = create_engine(settings.DATABASE_URL)
    VerifySession = sessionmaker(bind=verify_engine)
    with VerifySession() as vsession:
        fresh_run = vsession.get(Run, run_id)
        assert fresh_run is not None
        assert fresh_run.status == RunStatus.INVALID.value
        assert fresh_run.error_code == "invalid_input"
        assert fresh_run.generation_started_at is None


def test_start_run_maps_interrupt_to_awaiting_input(db):
    """Worker must set status='awaiting_input' and persist pending_interaction when interrupted."""
    from apps.api.workers.jobs import start_run

    run = Run(
        original_input="Cloud computing",
        status=RunStatus.QUEUED.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    interrupt_payload = {
        "type": "needs_clarification",
        "question": "What aspect of cloud computing?",
        "options": ["Serverless", "Kubernetes", "Cost optimization"],
    }

    with patch("apps.api.workers.jobs.agent_run", return_value={}):
        with patch("apps.api.workers.jobs.create_checkpointer") as mock_cp:
            mock_handle = MagicMock()
            mock_handle.close = MagicMock()
            mock_cp.return_value = mock_handle
            with patch("apps.api.workers.jobs._get_interrupt_payload", return_value=interrupt_payload):
                start_run(run_id)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    verify_engine = create_engine(settings.DATABASE_URL)
    VerifySession = sessionmaker(bind=verify_engine)
    with VerifySession() as vsession:
        fresh_run = vsession.get(Run, run_id)
        assert fresh_run is not None
        assert fresh_run.status == RunStatus.AWAITING_INPUT.value
        assert fresh_run.pending_interaction == interrupt_payload


def test_handle_run_failure_sets_failed_status():
    """_handle_run_failure must mark run as FAILED with error_code='generation_failed'."""
    from apps.api.workers.jobs import _handle_run_failure
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_engine = create_engine(settings.DATABASE_URL)
    DBSession = sessionmaker(bind=db_engine)

    with DBSession() as session:
        run = Run(
            original_input="Failure test topic",
            status=RunStatus.RUNNING.value,
        )
        session.add(run)
        session.commit()
        run_id = run.id

    _handle_run_failure(run_id, RuntimeError("Something went wrong"))

    with DBSession() as session:
        fresh = session.get(Run, run_id)
        assert fresh.status == RunStatus.FAILED.value
        assert fresh.error_code == "generation_failed"
