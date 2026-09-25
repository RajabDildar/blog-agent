"""PostgreSQL diagnostics sink implementation bridging core agent diagnostics to run_events."""
from __future__ import annotations

import threading
from typing import Any, Optional
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session, sessionmaker

from apps.api.db.session import engine
from apps.api.db.models import Run, RunEvent

# Thread-safe session factory for worker execution
WorkerSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

STABLE_EVENT_VOCABULARY = {
    "run_queued",
    "intent_check",
    "clarification_required",
    "topic_confirmation_required",
    "topic_finalized",
    "node_started",
    "node_succeeded",
    "node_failed",
    "research",
    "planning",
    "writing",
    "citation_verification",
    "editorial_review",
    "revision",
    "article_validation",
    "image_planning",
    "image_generation",
    "final_validation",
    "saving",
    "run_paused",
    "run_failed",
    "run_finished",
}

EVENT_MAPPING = {
    "intent_check_started": "intent_check",
    "intent_provider_fallback": "intent_check",
    "intent_check_succeeded": "intent_check",
    "clarification_required": "clarification_required",
    "topic_confirmation_required": "topic_confirmation_required",
    "topic_finalized": "topic_finalized",
    "input_blocked": "run_failed",
    "input_invalid": "run_failed",
    "input_cancelled": "run_failed",
    "node_started": "node_started",
    "node_succeeded": "node_succeeded",
    "node_failed": "node_failed",
    "paused_rate_limit": "run_paused",
    "finish_failure": "run_failed",
    "finish_success": "run_finished",
    "run_resumed": "node_started",
}


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitize event payload to ensure no internal Python tracebacks or secrets leak."""
    clean = {}
    for k, v in payload.items():
        if k in ("traceback", "stack_trace", "exc_info", "raw_exception"):
            continue
        if isinstance(v, Exception):
            clean[k] = str(v)
        elif isinstance(v, (str, int, float, bool, list, dict)) or v is None:
            clean[k] = v
        else:
            clean[k] = str(v)
    return clean


class PostgresDiagnosticsSink:
    """
    Diagnostics sink that persists events to PostgreSQL `run_events` table
    and updates `runs.diagnostics_summary`.
    """

    def __init__(self, run_id: str, session_factory: Optional[sessionmaker] = None):
        self.run_id = run_id
        self.session_factory = session_factory or WorkerSessionLocal
        self._lock = threading.Lock()
        self._sequence: Optional[int] = None

    def _get_next_sequence(self, session: Session) -> int:
        with self._lock:
            if self._sequence is None:
                max_seq = session.scalar(
                    select(func.coalesce(func.max(RunEvent.sequence), 0)).where(
                        RunEvent.run_id == self.run_id
                    )
                )
                self._sequence = int(max_seq or 0)
            self._sequence += 1
            return self._sequence

    def record_event(self, run_id: str, event: dict[str, Any]) -> None:
        raw_event_type = event.get("event", "node_started")
        mapped_event_type = EVENT_MAPPING.get(raw_event_type, raw_event_type)
        if mapped_event_type not in STABLE_EVENT_VOCABULARY:
            # Fall back to node_started or node_succeeded
            mapped_event_type = "node_started"

        stage = event.get("node") or event.get("stage")
        message = event.get("message")
        if not message:
            if mapped_event_type == "node_started" and stage:
                message = f"Started stage: {stage}"
            elif mapped_event_type == "node_succeeded" and stage:
                message = f"Finished stage: {stage}"
            elif mapped_event_type == "node_failed" and stage:
                message = f"Failed stage: {stage}"

        # Clean payload
        payload = sanitize_payload({k: v for k, v in event.items() if k not in ("event", "node", "stage", "message", "timestamp")})

        with self.session_factory() as session:
            try:
                seq = self._get_next_sequence(session)
                run_event = RunEvent(
                    run_id=self.run_id,
                    sequence=seq,
                    event_type=mapped_event_type,
                    stage=str(stage) if stage else None,
                    message=str(message) if message else None,
                    payload=payload if payload else None,
                )
                session.add(run_event)
                session.commit()
            except Exception:
                session.rollback()

    def record_summary(self, run_id: str, summary: dict[str, Any]) -> None:
        """Update runs.diagnostics_summary in the database."""
        with self.session_factory() as session:
            try:
                # Do not write events array inside diagnostics_summary JSON to avoid huge bloat
                clean_summary = dict(summary)
                if "events" in clean_summary:
                    clean_summary["events_count"] = len(clean_summary.pop("events"))

                session.execute(
                    update(Run)
                    .where(Run.id == self.run_id)
                    .values(diagnostics_summary=clean_summary)
                )
                session.commit()
            except Exception:
                session.rollback()
