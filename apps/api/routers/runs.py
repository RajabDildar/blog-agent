"""Runs router implementing run creation, retrieval, ownership filtering, and visibility updates."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.dependencies import (
    get_db,
    get_current_user_optional,
    get_current_admin,
    get_anonymous_id,
    verify_csrf,
)
from apps.api.db.models import User, Run
from apps.api.schemas.runs import (
    RunCreateRequest,
    RunResponse,
    RunListItemResponse,
    RunVisibilityUpdateRequest,
    RunFeatureUpdateRequest,
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
    Creates a durable queued run in PostgreSQL without running generation in-process.
    """
    user_id = current_user.id if current_user else None
    anon_id = None if user_id else get_anonymous_id(request, response)

    try:
        run = create_run(
            db,
            original_input=payload.input,
            user_id=user_id,
            anonymous_session_id=anon_id,
        )
    except RunInvariantError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

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


# --- Phase 4 Placeholders ---

@router.post("/{run_id}/input")
def submit_human_input(run_id: str):
    """Placeholder: human-in-the-loop clarification input becomes operational in Phase 4."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Human clarification input is operational in Phase 4 (RQ worker)",
    )


@router.post("/{run_id}/resume")
def resume_paused_run(run_id: str):
    """Placeholder: rate-limit/provider resume becomes operational in Phase 4."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Run resume is operational in Phase 4 (RQ worker)",
    )


@router.get("/{run_id}/events")
def stream_run_events(run_id: str):
    """Placeholder: Server-Sent Events stream becomes operational in Phase 4."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SSE event stream is operational in Phase 4",
    )
