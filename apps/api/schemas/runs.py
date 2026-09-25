"""Pydantic schemas for runs, gallery, and visibility mutations."""
from datetime import datetime
from typing import Optional, Any, List
from pydantic import BaseModel, Field, ConfigDict
from apps.api.db.models import RunStatus, RunVisibility


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
    user_id: Optional[str] = None
    # anonymous_session_id is intentionally excluded: it is an internal tracking
    # identifier that must not be exposed to API clients.
    original_input: str
    topic: Optional[str] = None
    status: str
    mode: Optional[str] = None
    visibility: str
    featured: bool
    pending_interaction: Optional[Any] = None
    created_at: datetime
    updated_at: datetime
    generation_started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    resume_after: Optional[datetime] = None
    diagnostics_summary: Optional[Any] = None
    article_object_key: Optional[str] = None
    article_title: Optional[str] = None
    article_excerpt: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    run_url: Optional[str] = None


class RunListItemResponse(BaseModel):
    """Summary item for listing user/anonymous runs."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_input: str
    topic: Optional[str] = None
    status: str
    visibility: str
    featured: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
    article_title: Optional[str] = None
    run_url: Optional[str] = None


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
    article_title: Optional[str] = None
    article_excerpt: Optional[str] = None
    topic: Optional[str] = None
    featured: bool
    completed_at: Optional[datetime] = None
    article_url: Optional[str] = None
