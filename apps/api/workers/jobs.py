"""Compatibility adapter forwarding execution to apps.api.inngest.functions."""
from __future__ import annotations

from apps.api.inngest.functions import (
    execute_start_run as start_run,
    execute_resume_run as resume_run,
    _handle_run_outcome,
    _handle_rate_limit_pause,
    _handle_run_failure,
    _get_interrupt_payload,
)

__all__ = [
    "start_run",
    "resume_run",
    "_handle_run_outcome",
    "_handle_rate_limit_pause",
    "_handle_run_failure",
    "_get_interrupt_payload",
]
