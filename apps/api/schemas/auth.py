"""Pydantic schemas for authentication requests and responses."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class GoogleAuthRequest(BaseModel):
    """Payload received from the frontend Google Identity Services button."""
    credential: str = Field(..., description="Google ID Token JWT")


class UserResponse(BaseModel):
    """Public user profile response."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_admin: bool
    created_at: datetime


class GoogleIdPayload(BaseModel):
    """Normalized payload extracted from a verified Google ID token."""
    google_sub: str
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
