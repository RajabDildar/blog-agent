"""Anonymous run claim service upon user authentication."""
from typing import List
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from apps.api.db.models import Run


def claim_anonymous_runs(
    db: Session,
    anonymous_session_id: str,
    user_id: str,
) -> List[Run]:
    """
    Transfers unowned runs tied to `anonymous_session_id` to the newly authenticated `user_id`.
    Clears `anonymous_session_id` so the run is now strictly owned by the user account.
    Preserves the exact `run.id` and any existing generated artifacts/URLs.
    Returns the list of claimed runs.
    """
    if not anonymous_session_id or not user_id:
        return []

    # Find runs owned by this anonymous identifier that do not already belong to a user
    stmt = select(Run).where(
        Run.anonymous_session_id == anonymous_session_id,
        Run.user_id.is_(None),
    )
    eligible_runs = list(db.scalars(stmt).all())
    if not eligible_runs:
        return []

    for run in eligible_runs:
        run.user_id = user_id
        run.anonymous_session_id = None

    db.commit()
    for run in eligible_runs:
        db.refresh(run)

    return eligible_runs
