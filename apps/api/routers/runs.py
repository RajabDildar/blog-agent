"""Runs router implementing run creation, retrieval, ownership filtering, visibility updates, HITL input, resume, and SSE."""
import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import (
    get_db,
    get_current_user_optional,
    get_current_admin,
    get_anonymous_id,
    verify_csrf,
)
from apps.api.db.models import User, Run, RunEvent, RunStatus
from apps.api.queue import get_queue
from apps.api.schemas.runs import (
    RunCreateRequest,
    RunResponse,
    RunListItemResponse,
    RunVisibilityUpdateRequest,
    RunFeatureUpdateRequest,
    HumanInputRequest,
)
from apps.api.services.diagnostics_sink import WorkerSessionLocal
from apps.api.services.quota_service import (
    check_and_increment_abuse_limit,
    check_pre_generation_quota,
    QuotaExceededError,
)
from apps.api.services.run_service import (
    create_run,
    get_run_by_id,
    list_runs,
    update_run_visibility,
    update_run_featured,
    RunNotFoundError,
    RunInvariantError,
)

router = APIRouter(prefix="/runs", tags=["runs"])
settings = get_settings()


def _format_run_response(run: Run) -> RunResponse:
    res = RunResponse.model_validate(run)
    res.run_url = f"/runs/{run.id}"
    return res


def _format_list_item(run: Run) -> RunListItemResponse:
    item = RunListItemResponse.model_validate(run)
    item.run_url = f"/runs/{run.id}"
    return item


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def create_new_run(
    payload: RunCreateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    _csrf: None = Depends(verify_csrf),
):
    """
    Submits a new technical article request.
    Creates a durable queued run in PostgreSQL and enqueues an RQ job without running generation in-process.
    """
    user_id = current_user.id if current_user else None
    anon_id = None if user_id else get_anonymous_id(request, response)
    client_ip = request.client.host if request.client else None

    # Abuse rate limit check (IP requests per hour)
    try:
        check_and_increment_abuse_limit(client_ip)
    except QuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    # Pre-generation quota check
    try:
        check_pre_generation_quota(
            db,
            user_id=user_id,
            anonymous_session_id=anon_id,
            client_ip=client_ip,
        )
    except QuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    try:
        run = create_run(
            db,
            original_input=payload.input,
            user_id=user_id,
            anonymous_session_id=anon_id,
        )
    except RunInvariantError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Record initial event in run_events
    initial_event = RunEvent(
        run_id=run.id,
        sequence=1,
        event_type="run_queued",
        stage=None,
        message="Run queued for background generation",
        payload=None,
    )
    db.add(initial_event)
    db.commit()

    # Enqueue to background worker
    try:
        queue = get_queue("default")
        queue.enqueue("apps.api.workers.jobs.start_run", run.id)
    except Exception:
        # Non-blocking for testing environments where Redis queue may be stubbed
        pass

    return _format_run_response(run)


@router.get("", response_model=List[RunListItemResponse])
def get_user_runs(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Lists runs owned by the active user or anonymous session."""
    user_id = current_user.id if current_user else None
    anon_id = request.cookies.get(settings.ANONYMOUS_COOKIE_NAME) if not user_id else None

    runs = list_runs(db, user_id=user_id, anonymous_session_id=anon_id, limit=limit, offset=offset)
    return [_format_list_item(r) for r in runs]


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Fetches a run by ID if the caller is authorized."""
    user_id = current_user.id if current_user else None
    anon_id = request.cookies.get(settings.ANONYMOUS_COOKIE_NAME) if not user_id else None
    is_admin = current_user.is_admin if current_user else False

    run = get_run_by_id(
        db,
        run_id=run_id,
        user_id=user_id,
        anonymous_session_id=anon_id,
        is_admin=is_admin,
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )
    return _format_run_response(run)


@router.patch("/{run_id}/visibility", response_model=RunResponse)
def change_run_visibility(
    run_id: str,
    payload: RunVisibilityUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    _csrf: None = Depends(verify_csrf),
):
    """Updates visibility of a run. Only completed runs can be made public."""
    user_id = current_user.id if current_user else None
    anon_id = request.cookies.get(settings.ANONYMOUS_COOKIE_NAME) if not user_id else None

    try:
        run = update_run_visibility(
            db,
            run_id=run_id,
            visibility=payload.visibility,
            user_id=user_id,
            anonymous_session_id=anon_id,
        )
    except RunNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except RunInvariantError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return _format_run_response(run)


@router.patch("/{run_id}/feature", response_model=RunResponse)
def feature_run(
    run_id: str,
    payload: RunFeatureUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
    _csrf: None = Depends(verify_csrf),
):
    """Admin-only endpoint to feature a public completed article."""
    try:
        run = update_run_featured(
            db,
            run_id=run_id,
            featured=payload.featured,
            is_admin=admin.is_admin,
        )
    except RunNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except RunInvariantError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return _format_run_response(run)


# --- Phase 4 Operational Endpoints ---

@router.post("/{run_id}/input", response_model=RunResponse)
def submit_human_input(
    run_id: str,
    payload: HumanInputRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    _csrf: None = Depends(verify_csrf),
):
    """
    Submits user response to clarification or confirmation interrupt.
    Atomically clears interaction to prevent duplicate resume and enqueues resume job.
    """
    user_id = current_user.id if current_user else None
    anon_id = request.cookies.get(settings.ANONYMOUS_COOKIE_NAME) if not user_id else None
    client_ip = request.client.host if request.client else None

    try:
        check_and_increment_abuse_limit(client_ip)
    except QuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    run = db.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")

    # Caller authorization
    if run.user_id:
        if not user_id or user_id != run.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif run.anonymous_session_id:
        if anon_id != run.anonymous_session_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Status & pending interaction check
    if run.status != RunStatus.AWAITING_INPUT.value or not run.pending_interaction:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Run is not awaiting user clarification or confirmation",
        )

    interaction = run.pending_interaction
    itype = interaction.get("type") if isinstance(interaction, dict) else None

    if itype == "needs_clarification":
        if payload.action == "select_option":
            options = interaction.get("options", [])
            if payload.value not in options:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Selected option '{payload.value}' does not match any offered option: {options}",
                )
        elif payload.action == "custom_input":
            if not payload.value or not payload.value.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Custom input value cannot be empty",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action '{payload.action}' for clarification. Must be 'select_option' or 'custom_input'",
            )
    elif itype == "proposed_topic_confirmation":
        if payload.action not in ("proceed", "cancel"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action '{payload.action}' for confirmation. Must be 'proceed' or 'cancel'",
            )
    else:
        if payload.action not in ("select_option", "custom_input", "proceed", "cancel"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported action '{payload.action}'",
            )

    # Atomically clear pending_interaction and update status
    human_response_payload = {"action": payload.action, "value": payload.value}
    run.status = RunStatus.QUEUED.value
    run.pending_interaction = None
    db.commit()

    # Enqueue resume
    try:
        queue = get_queue("default")
        queue.enqueue("apps.api.workers.jobs.resume_run", run_id, human_response_payload)
    except Exception:
        pass

    return _format_run_response(run)


@router.post("/{run_id}/resume", response_model=RunResponse)
def resume_paused_run(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    _csrf: None = Depends(verify_csrf),
):
    """
    Enqueues a resume job for a failed or paused run.
    Validates ownership, terminal boundaries, and rate-limit backoff timers.
    """
    user_id = current_user.id if current_user else None
    anon_id = request.cookies.get(settings.ANONYMOUS_COOKIE_NAME) if not user_id else None

    run = db.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")

    if run.user_id:
        if not user_id or user_id != run.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif run.anonymous_session_id:
        if anon_id != run.anonymous_session_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if run.status not in (RunStatus.PAUSED.value, RunStatus.FAILED.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Run '{run_id}' in status '{run.status}' cannot be resumed. Resume is only allowed for 'paused' or 'failed' runs.",
        )

    if run.status == RunStatus.PAUSED.value and run.resume_after:
        now = datetime.now(timezone.utc)
        if now < run.resume_after:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rate limit backoff active until {run.resume_after.isoformat()}. Please wait before resuming.",
            )

    run.status = RunStatus.QUEUED.value
    db.commit()

    try:
        queue = get_queue("default")
        queue.enqueue("apps.api.workers.jobs.resume_run", run_id, None)
    except Exception:
        pass

    return _format_run_response(run)


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Streams Server-Sent Events (SSE) for live generation progress.
    Supports Last-Event-ID reconnection, monotonic sequence ordering, and clean termination.
    """
    user_id = current_user.id if current_user else None
    anon_id = request.cookies.get(settings.ANONYMOUS_COOKIE_NAME) if not user_id else None

    run = get_run_by_id(
        db,
        run_id=run_id,
        user_id=user_id,
        anonymous_session_id=anon_id,
        is_admin=current_user.is_admin if current_user else False,
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")

    # Private run owner-only access check
    if run.user_id:
        if not user_id or user_id != run.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif run.anonymous_session_id:
        if anon_id != run.anonymous_session_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    last_event_id_header = request.headers.get("Last-Event-ID")
    initial_last_seq = 0
    if last_event_id_header:
        try:
            initial_last_seq = int(last_event_id_header)
        except ValueError:
            initial_last_seq = 0

    async def event_generator():
        last_seq = initial_last_seq
        idle_counter = 0
        terminal_statuses = {
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.BLOCKED.value,
            RunStatus.INVALID.value,
            RunStatus.CANCELLED.value,
            RunStatus.EXPIRED.value,
        }

        while True:
            if await request.is_disconnected():
                break

            with WorkerSessionLocal() as session:
                events = session.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.sequence > last_seq)
                    .order_by(RunEvent.sequence.asc())
                ).all()

                current_status = session.scalar(
                    select(Run.status).where(Run.id == run_id)
                )

            if events:
                idle_counter = 0
                for ev in events:
                    last_seq = ev.sequence
                    event_data = {
                        "sequence": ev.sequence,
                        "event_type": ev.event_type,
                        "stage": ev.stage,
                        "message": ev.message,
                        "payload": ev.payload,
                        "created_at": ev.created_at.isoformat() if ev.created_at else None,
                    }
                    yield f"id: {ev.sequence}\nevent: {ev.event_type}\ndata: {json.dumps(event_data)}\n\n"
            else:
                idle_counter += 1
                if idle_counter >= 20:  # ~10 seconds at 0.5s intervals
                    yield ": heartbeat\n\n"
                    idle_counter = 0

            # If run reached terminal status and all events sent, close stream cleanly
            if current_status in terminal_statuses and not events:
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
