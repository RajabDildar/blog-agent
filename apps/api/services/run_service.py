"""Run and gallery service operations with strict ownership and invariant enforcement."""
from typing import Optional, List
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from apps.api.db.models import Run, RunStatus, RunVisibility


class RunNotFoundError(Exception):
    """Raised when run is not found or access is denied."""
    pass


class RunInvariantError(ValueError):
    """Raised when an application or domain invariant is violated."""
    pass


def create_run(
    db: Session,
    original_input: str,
    user_id: Optional[str] = None,
    anonymous_session_id: Optional[str] = None,
) -> Run:
    """
    Creates a new queued run record.
    Enforces that at least one ownership identifier is present.
    Does NOT invoke LangGraph generation inside the HTTP request.
    """
    cleaned_input = original_input.strip()
    if not cleaned_input:
        raise RunInvariantError("original_input cannot be empty")

    if not user_id and not anonymous_session_id:
        raise RunInvariantError("Run must have either user_id or anonymous_session_id")

    run = Run(
        user_id=user_id,
        anonymous_session_id=anonymous_session_id if not user_id else None,
        original_input=cleaned_input,
        topic=None,
        status=RunStatus.QUEUED.value,
        visibility=RunVisibility.PRIVATE.value,
        featured=False,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run_by_id(
    db: Session,
    run_id: str,
    user_id: Optional[str] = None,
    anonymous_session_id: Optional[str] = None,
    is_admin: bool = False,
) -> Optional[Run]:
    """
    Fetches a run by ID enforcing strict authorization:
    - Public completed runs are readable by anyone.
    - Authenticated users can only read their own runs.
    - Anonymous users can only read runs matching their anonymous cookie.
    - Admin status does NOT grant broad access to arbitrary private runs.
    """
    stmt = select(Run).where(Run.id == run_id)
    run = db.scalar(stmt)
    if not run:
        return None

    # Public completed runs are accessible to all
    if run.visibility == RunVisibility.PUBLIC.value and run.status == RunStatus.COMPLETED.value:
        return run

    # Owner access check
    if user_id and run.user_id == user_id:
        return run

    if (
        anonymous_session_id
        and not run.user_id
        and run.anonymous_session_id == anonymous_session_id
    ):
        return run

    # Admins inspecting a public run or their own run is handled above.
    # Strict isolation: access denied for private runs belonging to others.
    return None


def list_runs(
    db: Session,
    user_id: Optional[str] = None,
    anonymous_session_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Run]:
    """Lists runs owned by the authenticated user or anonymous session."""
    stmt = select(Run)

    if user_id:
        stmt = stmt.where(Run.user_id == user_id)
    elif anonymous_session_id:
        stmt = stmt.where(
            Run.anonymous_session_id == anonymous_session_id,
            Run.user_id.is_(None),
        )
    else:
        return []

    stmt = stmt.order_by(desc(Run.created_at)).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


def update_run_visibility(
    db: Session,
    run_id: str,
    visibility: RunVisibility,
    user_id: Optional[str] = None,
    anonymous_session_id: Optional[str] = None,
) -> Run:
    """
    Updates run visibility with ownership and status invariant verification:
    - Only the run owner may update visibility.
    - visibility=public is legal ONLY for completed runs.
    - Changing to private clears featured=True.
    """
    stmt = select(Run).where(Run.id == run_id)
    run = db.scalar(stmt)
    if not run:
        raise RunNotFoundError(f"Run {run_id} not found")

    # Ownership check
    is_owner = False
    if user_id and run.user_id == user_id:
        is_owner = True
    elif (
        anonymous_session_id
        and not run.user_id
        and run.anonymous_session_id == anonymous_session_id
    ):
        is_owner = True

    if not is_owner:
        raise PermissionError("Only the owner can modify run visibility")

    target_val = visibility.value if isinstance(visibility, RunVisibility) else visibility
    if target_val == RunVisibility.PUBLIC.value and run.status != RunStatus.COMPLETED.value:
        raise RunInvariantError("Only completed runs can be made public")

    run.visibility = target_val
    if target_val == RunVisibility.PRIVATE.value and run.featured:
        run.featured = False

    db.commit()
    db.refresh(run)
    return run


def update_run_featured(
    db: Session,
    run_id: str,
    featured: bool,
    is_admin: bool,
) -> Run:
    """
    Updates article featured status:
    - Only administrators can feature/unfeature.
    - featured=true requires visibility=public AND status=completed.
    - Admin cannot feature private or non-completed runs.
    """
    if not is_admin:
        raise PermissionError("Administrator privileges required to feature articles")

    stmt = select(Run).where(Run.id == run_id)
    run = db.scalar(stmt)
    if not run:
        raise RunNotFoundError(f"Run {run_id} not found")

    if featured:
        if run.visibility != RunVisibility.PUBLIC.value:
            raise RunInvariantError("Cannot feature a private run; run must be public")
        if run.status != RunStatus.COMPLETED.value:
            raise RunInvariantError("Cannot feature an incomplete run; run must be completed")

    run.featured = featured
    db.commit()
    db.refresh(run)
    return run


def get_gallery(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> List[Run]:
    """Retrieves all public, completed articles for the community gallery."""
    stmt = (
        select(Run)
        .where(
            Run.visibility == RunVisibility.PUBLIC.value,
            Run.status == RunStatus.COMPLETED.value,
        )
        .order_by(desc(Run.completed_at), desc(Run.created_at))
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())


def get_featured(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> List[Run]:
    """Retrieves all featured, public, completed articles."""
    stmt = (
        select(Run)
        .where(
            Run.featured.is_(True),
            Run.visibility == RunVisibility.PUBLIC.value,
            Run.status == RunStatus.COMPLETED.value,
        )
        .order_by(desc(Run.completed_at), desc(Run.created_at))
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())
