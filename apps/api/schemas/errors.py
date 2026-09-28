"""Standardized error schemas and response helper for API contract (Section 16)."""
from typing import Optional
from pydantic import BaseModel
from fastapi import HTTPException


class ErrorDetail(BaseModel):
    code: str
    message: str
    run_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error_response(
    status_code: int,
    code: str,
    message: str,
    run_id: Optional[str] = None,
    headers: Optional[dict] = None,
) -> HTTPException:
    """Builds a standard HTTPException adhering to {"error": {"code", "message", "run_id"}}."""
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "code": code,
                "message": message,
                "run_id": run_id,
            }
        },
        headers=headers,
    )
