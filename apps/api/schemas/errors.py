"""Standardized error schemas and response helper for API contract (Section 16)."""

from fastapi import HTTPException
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    run_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error_response(
    status_code: int,
    code: str,
    message: str,
    run_id: str | None = None,
    headers: dict | None = None,
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
