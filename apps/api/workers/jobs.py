"""RQ worker jobs for asynchronous run execution and HITL resumption."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db.session import engine
from apps.api.db.models import Run, RunStatus
from apps.api.services.diagnostics_sink import PostgresDiagnosticsSink, WorkerSessionLocal
from apps.api.services.quota_service import reserve_generation_quota_atomic
from blog_agent import run as agent_run, resume as agent_resume
from blog_agent.schemas.models import IntentHumanResponse
from blog_agent.services.checkpointer import create_checkpointer
from blog_agent.services.rate_limits import RateLimitRetryExhausted

logger = logging.getLogger("blog_agent.worker")
settings = get_settings()


def _get_interrupt_payload(checkpointer_handle, run_id: str) -> Optional[dict[str, Any]]:
    """Inspects checkpointer state to extract pending interrupt payload if present."""
    from blog_agent.graph.main_graph import build_graph, _thread_config
    graph = build_graph(checkpointer_handle.saver)
    state = graph.get_state(_thread_config(run_id))
    tasks = getattr(state, "tasks", None)
    if tasks and getattr(tasks[0], "interrupts", None):
        first_interrupt = tasks[0].interrupts[0]
        val = getattr(first_interrupt, "value", first_interrupt)
        if isinstance(val, dict):
            return val
    return None


def start_run(run_id: str) -> None:
    """RQ background job to start execution of a queued run."""
    with WorkerSessionLocal() as session:
        run_record = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if not run_record:
            logger.error(f"Run {run_id} not found in database.")
            return

        if run_record.status not in (RunStatus.QUEUED.value, RunStatus.RUNNING.value):
            logger.warning(f"Run {run_id} is in status '{run_record.status}', skipping start.")
            return

        run_record.status = RunStatus.RUNNING.value
        session.commit()
        original_input = run_record.original_input

    sink = PostgresDiagnosticsSink(run_id)
    handle = create_checkpointer(backend=settings.CHECKPOINT_BACKEND)

    try:
        result = agent_run(
            original_input,
            run_id=run_id,
            diagnostics_sink=sink,
            checkpointer_handle=handle,
        )
        _handle_run_outcome(run_id, result, handle)
    except RateLimitRetryExhausted as exc:
        _handle_rate_limit_pause(run_id, exc)
    except Exception as exc:
        logger.exception(f"Run {run_id} failed with exception: {exc}")
        _handle_run_failure(run_id, exc)
    finally:
        handle.close()


def resume_run(run_id: str, human_response: Optional[dict[str, Any]] = None) -> None:
    """RQ background job to resume an interrupted, paused, or failed run."""
    with WorkerSessionLocal() as session:
        run_record = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if not run_record:
            logger.error(f"Run {run_id} not found in database.")
            return

        run_record.status = RunStatus.RUNNING.value
        session.commit()

    sink = PostgresDiagnosticsSink(run_id)
    handle = create_checkpointer(backend=settings.CHECKPOINT_BACKEND)

    parsed_response = None
    if human_response:
        parsed_response = IntentHumanResponse.model_validate(human_response)

    try:
        result = agent_resume(
            run_id=run_id,
            human_response=parsed_response,
            diagnostics_sink=sink,
            checkpointer_handle=handle,
        )
        _handle_run_outcome(run_id, result, handle)
    except RateLimitRetryExhausted as exc:
        _handle_rate_limit_pause(run_id, exc)
    except Exception as exc:
        logger.exception(f"Resume for run {run_id} failed with exception: {exc}")
        _handle_run_failure(run_id, exc)
    finally:
        handle.close()


def _handle_run_outcome(run_id: str, result: dict[str, Any], handle) -> None:
    """Maps core graph outcome to persistent database status and fields."""
    interrupt_payload = _get_interrupt_payload(handle, run_id)

    with WorkerSessionLocal() as session:
        run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if not run:
            return

        if interrupt_payload:
            run.status = RunStatus.AWAITING_INPUT.value
            run.pending_interaction = interrupt_payload
            session.commit()
            return

        intent_status = result.get("intent_status")

        if intent_status == "blocked":
            run.status = RunStatus.BLOCKED.value
            run.error_code = "input_blocked"
            run.error_message = (
                result.get("intent_message")
                or "The provided request violates content safety policy."
            )
            run.pending_interaction = None
            session.commit()
            return

        if intent_status == "invalid":
            run.status = RunStatus.INVALID.value
            run.error_code = "invalid_input"
            run.error_message = (
                result.get("intent_message")
                or "The provided topic is invalid or out of scope for technical blogging."
            )
            run.pending_interaction = None
            session.commit()
            return

        if intent_status == "cancelled":
            run.status = RunStatus.CANCELLED.value
            run.pending_interaction = None
            session.commit()
            return

        # Topic finalized - reserve quota if not yet reserved
        finalized_topic = result.get("topic")
        if finalized_topic:
            run.topic = finalized_topic

        run.pending_interaction = None

        if run.generation_started_at is None:
            quota_ok = reserve_generation_quota_atomic(session, run_id)
            if not quota_ok:
                return

        # Graph ran to completion
        run.status = RunStatus.COMPLETED.value
        run.completed_at = datetime.now(timezone.utc)
        if result.get("saved_path"):
            run.article_object_key = result["saved_path"]
        session.commit()


def _handle_rate_limit_pause(run_id: str, exc: RateLimitRetryExhausted) -> None:
    """Updates run to paused status with resume_after timestamp."""
    resume_after_dt = (
        datetime.fromtimestamp(exc.resume_after, tz=timezone.utc)
        if getattr(exc, "resume_after", None)
        else None
    )
    with WorkerSessionLocal() as session:
        session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                status=RunStatus.PAUSED.value,
                resume_after=resume_after_dt,
                error_code="rate_limit_paused",
                error_message="Provider rate limit reached. Generation is paused and will resume automatically.",
            )
        )
        session.commit()


def _handle_run_failure(run_id: str, exc: Exception) -> None:
    """Updates run to failed status with sanitized user-facing error message."""
    with WorkerSessionLocal() as session:
        session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                status=RunStatus.FAILED.value,
                error_code="generation_failed",
                error_message="An internal error occurred during article generation. Please try again.",
            )
        )
        session.commit()
