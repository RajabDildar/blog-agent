"""Pydantic schemas for runs, gallery, and visibility mutations."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.api.db.models import RunVisibility


class RunCreateRequest(BaseModel):
    """Initial article request submitted from the frontend composer."""

    input: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User topic or technical article request",
    )


class RunResponse(BaseModel):
    """Detailed response for a single run."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None = None
    # anonymous_session_id is intentionally excluded: it is an internal tracking
    # identifier that must not be exposed to API clients.
    original_input: str
    topic: str | None = None
    status: str
    mode: str | None = None
    visibility: str
    featured: bool
    pending_interaction: Any | None = None
    created_at: datetime
    updated_at: datetime
    generation_started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    resume_after: datetime | None = None
    diagnostics_summary: Any | None = None
    article_markdown: str | None = None
    article_assets: Any | None = None
    article_title: str | None = None
    article_excerpt: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    can_resume: bool = False
    safe_alternatives: list[str] | None = None
    run_url: str | None = None


class PublicRunResponse(BaseModel):
    """Public-safe summary of a completed run for non-owners."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    topic: str | None = None
    article_title: str | None = None
    article_excerpt: str | None = None
    article_url: str | None = None
    visibility: str
    completed_at: datetime | None = None


class ArticleResponse(BaseModel):
    """Detailed response for a completed technical article."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    article_title: str | None = None
    article_excerpt: str | None = None
    article_markdown: str | None = None
    topic: str | None = None
    completed_at: datetime | None = None
    visibility: str
    featured: bool
    article_assets: Any | None = None
    article_url: str | None = None


class RunListItemResponse(BaseModel):
    """Summary item for listing user/anonymous runs."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    original_input: str
    topic: str | None = None
    status: str
    visibility: str
    featured: bool
    created_at: datetime
    completed_at: datetime | None = None
    article_title: str | None = None
    run_url: str | None = None


class RunVisibilityUpdateRequest(BaseModel):
    """Request payload to change run visibility."""

    visibility: RunVisibility


class RunFeatureUpdateRequest(BaseModel):
    """Request payload for admin to feature/unfeature an article."""

    featured: bool


class GalleryItemResponse(BaseModel):
    """Public gallery technical article summary."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    article_title: str | None = None
    article_excerpt: str | None = None
    topic: str | None = None
    featured: bool
    completed_at: datetime | None = None
    article_url: str | None = None


class HumanInputRequest(BaseModel):
    """User response to clarification or confirmation interrupt."""

    action: str = Field(
        ...,
        description="Action type: select_option | custom_input | proceed | cancel",
    )
    value: str | None = Field(
        None,
        max_length=1000,
        description="Selected option value or custom input string",
    )
