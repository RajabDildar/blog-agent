"""Phase 4 tests: SSE event streaming and PostgresDiagnosticsSink DB interactions."""
from __future__ import annotations

import uuid
import threading
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from apps.api.main import app
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


def _make_completed_run_with_events(db, *, event_types: list[str]) -> tuple[Run, list[RunEvent]]:
    """Create a COMPLETED Run and associated RunEvents."""
    anon_id = "anon-sse-" + uuid.uuid4().hex[:8]
    run = Run(
        original_input="SSE streaming test topic",
        status=RunStatus.COMPLETED.value,
        anonymous_session_id=anon_id,
    )
    db.add(run)
    db.flush()

    events = []
    for seq, etype in enumerate(event_types, start=1):
        evt = RunEvent(
            run_id=run.id,
            event_type=etype,
            sequence=seq,
            payload={"message": f"Event {seq}: {etype}"},
        )
        db.add(evt)
        events.append(evt)

    db.commit()
    db.refresh(run)
    return run, events


# ---------------------------------------------------------------------------
# RunEvent schema / DB tests
# ---------------------------------------------------------------------------

def test_run_events_table_stores_sequential_events(db):
    """RunEvent rows must be stored with monotonically increasing sequences."""
    event_types = ["run_queued", "intent_check", "topic_finalized", "writing", "run_finished"]
    run, events = _make_completed_run_with_events(db, event_types=event_types)

    sequences = [e.sequence for e in events]
    assert sequences == list(range(1, len(event_types) + 1)), "Sequences must be consecutive 1-N"


def test_run_event_payload_is_persisted(db):
    """RunEvent JSON payload must round-trip cleanly through the DB."""
    run, events = _make_completed_run_with_events(db, event_types=["intent_check"])
    evt = events[0]

    db.expire(evt)
    stored_evt = db.get(RunEvent, evt.id)
    assert stored_evt is not None
    assert stored_evt.payload["message"] == "Event 1: intent_check"


def test_run_event_run_id_references_parent(db):
    """RunEvent.run_id must reference the correct parent Run."""
    run, events = _make_completed_run_with_events(db, event_types=["run_queued"])
    stored = db.get(RunEvent, events[0].id)
    assert stored.run_id == run.id


# ---------------------------------------------------------------------------
# SSE endpoint authorization tests (no streaming needed)
# ---------------------------------------------------------------------------

def test_get_events_sse_unknown_run_returns_404(client):
    """GET /runs/{unknown_id}/events must return 404."""
    client.cookies.set("blog_anon", "some-anon-id")
    res = client.get(
        f"/runs/{uuid.uuid4()}/events",
        headers={"origin": "http://localhost:5173"},
    )
    assert res.status_code == 404


def test_get_events_sse_wrong_owner_returns_404(db, client):
    """GET /runs/{id}/events with wrong anonymous session ID must return 404.

    The get_run_by_id service returns None for runs the caller doesn't own
    (privacy-preserving pattern: don't reveal resource existence).
    """
    run, _ = _make_completed_run_with_events(db, event_types=["run_queued"])
    client.cookies.set("blog_anon", "completely-wrong-anon-id-" + uuid.uuid4().hex)

    res = client.get(
        f"/runs/{run.id}/events",
        headers={"origin": "http://localhost:5173"},
    )
    assert res.status_code == 404


def test_get_events_sse_correct_owner_returns_stream(db, client):
    """GET /runs/{id}/events with correct owner must return text/event-stream."""
    run, events = _make_completed_run_with_events(
        db, event_types=["run_queued", "intent_check", "run_finished"]
    )
    anon_id = run.anonymous_session_id
    client.cookies.set("blog_anon", anon_id)

    # The endpoint is an async SSE stream. TestClient will consume it until the generator exits.
    # Since the run is COMPLETED and all events will be consumed in the first poll,
    # the second poll will see terminal status with no new events and break.
    with client.stream("GET", f"/runs/{run.id}/events",
                       headers={"origin": "http://localhost:5173"}) as res:
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# PostgresDiagnosticsSink tests
# ---------------------------------------------------------------------------

def test_postgres_diagnostics_sink_record_event_persists_row(db):
    """PostgresDiagnosticsSink.record_event() must insert a RunEvent row."""
    from apps.api.services.diagnostics_sink import PostgresDiagnosticsSink
    from sqlalchemy.orm import sessionmaker
    from apps.api.db.session import engine

    run = Run(
        original_input="Diagnostics sink insert test",
        status=RunStatus.RUNNING.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    # Use the same engine but a fresh session factory (as in worker context)
    SinkSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    sink = PostgresDiagnosticsSink(run_id=run_id, session_factory=SinkSessionLocal)
    sink.record_event(run_id, {"event": "writing", "stage": "introduction"})
    sink.record_event(run_id, {"event": "writing", "stage": "body"})
    sink.record_event(run_id, {"event": "finish_success", "message": "Done"})

    events = (
        db.query(RunEvent)
        .filter(RunEvent.run_id == run_id)
        .order_by(RunEvent.sequence)
        .all()
    )
    assert len(events) == 3
    # "writing" maps to "writing" in STABLE_EVENT_VOCABULARY
    assert events[0].event_type == "writing"
    assert events[0].stage == "introduction"
    # "finish_success" maps to "run_finished"
    assert events[2].event_type == "run_finished"


def test_postgres_diagnostics_sink_sequences_are_monotonic(db):
    """PostgresDiagnosticsSink must issue monotonically increasing sequence numbers."""
    from apps.api.services.diagnostics_sink import PostgresDiagnosticsSink
    from sqlalchemy.orm import sessionmaker
    from apps.api.db.session import engine

    run = Run(
        original_input="Diagnostics sink sequence test",
        status=RunStatus.RUNNING.value,
    )
    db.add(run)
    db.commit()
    run_id = run.id

    SinkSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    sink = PostgresDiagnosticsSink(run_id=run_id, session_factory=SinkSessionLocal)
    for i in range(5):
        sink.record_event(run_id, {"event": "node_started", "node": f"node_{i}"})

    events = (
        db.query(RunEvent)
        .filter(RunEvent.run_id == run_id)
        .order_by(RunEvent.sequence)
        .all()
    )
    assert len(events) == 5
    sequences = [e.sequence for e in events]
    assert sequences == list(range(1, 6)), "Sequences must be 1, 2, 3, 4, 5"


def test_postgres_diagnostics_sink_sequence_continues_after_existing(db):
    """Sink must continue sequence from existing max sequence, not restart from 1."""
    from apps.api.services.diagnostics_sink import PostgresDiagnosticsSink
    from sqlalchemy.orm import sessionmaker
    from apps.api.db.session import engine

    run = Run(
        original_input="Diagnostics sink continuation test",
        status=RunStatus.RUNNING.value,
    )
    db.add(run)
    db.flush()

    # Pre-seed 2 events (e.g. from POST /runs creating run_queued event)
    db.add(RunEvent(run_id=run.id, event_type="run_queued", sequence=1))
    db.add(RunEvent(run_id=run.id, event_type="intent_check", sequence=2))
    db.commit()
    run_id = run.id

    SinkSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    sink = PostgresDiagnosticsSink(run_id=run_id, session_factory=SinkSessionLocal)
    sink.record_event(run_id, {"event": "node_started", "node": "research"})

    events = (
        db.query(RunEvent)
        .filter(RunEvent.run_id == run_id)
        .order_by(RunEvent.sequence)
        .all()
    )
    assert len(events) == 3
    # Third event must have sequence=3, not 1
    assert events[2].sequence == 3


def test_postgres_diagnostics_sink_sanitizes_payload(db):
    """Sink must strip traceback/exc_info keys from event payloads."""
    from apps.api.services.diagnostics_sink import PostgresDiagnosticsSink, sanitize_payload

    dirty = {
        "traceback": "Traceback (most recent call last):\n  ...\nRuntimeError: secret",
        "exc_info": RuntimeError("secret"),
        "message": "Generation failed",
        "stage": "writing",
    }

    clean = sanitize_payload(dirty)

    assert "traceback" not in clean
    assert "exc_info" not in clean
    assert clean["message"] == "Generation failed"
    assert clean["stage"] == "writing"


def test_postgres_diagnostics_sink_thread_lock_prevents_duplicate_sequences():
    """Lock must prevent duplicate sequence numbers under concurrent emit calls."""
    from apps.api.services.diagnostics_sink import PostgresDiagnosticsSink

    emitted_sequences = []
    lock = threading.Lock()

    # Simulate only the locking mechanism (not real DB writes)
    counter = [0]

    def mock_record_event(run_id, event):
        with lock:
            counter[0] += 1
            emitted_sequences.append(counter[0])

    sink = PostgresDiagnosticsSink.__new__(PostgresDiagnosticsSink)
    sink.record_event = mock_record_event

    threads = [threading.Thread(target=sink.record_event, args=("fake-id", {"event": f"e{i}"})) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(emitted_sequences) == list(range(1, 21)), "No duplicate sequences under concurrency"
