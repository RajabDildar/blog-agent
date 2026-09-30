"""Articles router for reading completed Markdown articles and delivering image assets."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.db.models import Run, RunStatus, RunVisibility, User
from apps.api.dependencies import get_current_user_optional, get_db
from apps.api.schemas.errors import error_response
from apps.api.schemas.runs import ArticleResponse
from blog_agent.services.cloudinary_storage import (
    generate_signed_image_url,
    is_cloudinary_configured,
)
from blog_agent.services.run_paths import published_images_dir, run_images_dir

router = APIRouter(prefix="/articles", tags=["articles"])
settings = get_settings()


def _format_article_response(run: Run) -> ArticleResponse:
    res = ArticleResponse.model_validate(run)
    res.article_url = f"/articles/{run.id}"
    return res


@router.get("/{run_id}", response_model=ArticleResponse)
def get_article_by_id(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Fetches a completed technical article by ID.
    Enforces that only completed public articles or completed owned private articles are readable.
    """
    user_id = current_user.id if current_user else None
    anon_id = (
        request.cookies.get(settings.ANONYMOUS_COOKIE_NAME) if not user_id else None
    )

    run = db.scalar(select(Run).where(Run.id == run_id))
    if not run or run.status != RunStatus.COMPLETED.value:
        raise error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=f"Article '{run_id}' not found",
            run_id=run_id,
        )

    # Public completed articles are accessible to anyone
    if run.visibility == RunVisibility.PUBLIC.value:
        return _format_article_response(run)

    # Private completed article owner check
    is_owner = False
    if (
        user_id
        and run.user_id == user_id
        or (anon_id and not run.user_id and run.anonymous_session_id == anon_id)
    ):
        is_owner = True

    if not is_owner:
        # Hide existence of private article from unauthorized callers
        raise error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=f"Article '{run_id}' not found",
            run_id=run_id,
        )

    return _format_article_response(run)


@router.get("/{run_id}/assets/{filename}")
def get_article_asset(
    run_id: str,
    filename: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Delivers an image asset for a completed article.
    Checks authorization and returns a 307 Temporary Redirect to a signed Cloudinary URL
    or serves the local image file in local dev mode.
    """
    user_id = current_user.id if current_user else None
    anon_id = (
        request.cookies.get(settings.ANONYMOUS_COOKIE_NAME) if not user_id else None
    )

    run = db.scalar(select(Run).where(Run.id == run_id))
    if not run:
        raise error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=f"Asset '{filename}' not found for run '{run_id}'",
            run_id=run_id,
        )

    # Authorization check
    if run.visibility != RunVisibility.PUBLIC.value:
        is_owner = False
        if (
            user_id
            and run.user_id == user_id
            or anon_id
            and not run.user_id
            and run.anonymous_session_id == anon_id
        ):
            is_owner = True

        if not is_owner:
            raise error_response(
                status_code=status.HTTP_404_NOT_FOUND,
                code="not_found",
                message=f"Asset '{filename}' not found",
                run_id=run_id,
            )

    # Asset manifest check
    assets = run.article_assets or []
    matching_asset = next(
        (a for a in assets if isinstance(a, dict) and a.get("filename") == filename),
        None,
    )

    # Try Cloudinary signed URL redirect if public_id is available
    if (
        matching_asset
        and matching_asset.get("public_id")
        and not matching_asset["public_id"].startswith("local:")
        and is_cloudinary_configured()
    ):
        signed_url = generate_signed_image_url(matching_asset["public_id"])
        return RedirectResponse(
            url=signed_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    # Local file fallback for CLI / testing environment
    pub_dir = published_images_dir(title=run.article_title or "", run_id=run_id)
    local_published_file = pub_dir / filename
    if local_published_file.is_file():
        return FileResponse(path=str(local_published_file))

    staged_file = run_images_dir(run_id) / filename
    if staged_file.is_file():
        return FileResponse(path=str(staged_file))

    raise error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="not_found",
        message=f"Asset file '{filename}' not found",
        run_id=run_id,
    )
