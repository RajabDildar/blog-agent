"""Event queue interface delegating to Inngest orchestration."""
from __future__ import annotations

from typing import Any
from apps.api.inngest import send_inngest_event


def enqueue_run_start(run_id: str) -> list[str]:
    """Emits blog-agent/run.start event."""
    return send_inngest_event("blog-agent/run.start", {"run_id": run_id})


def enqueue_run_resume(run_id: str, human_response: Any = None) -> list[str]:
    """Emits blog-agent/run.resume event."""
    return send_inngest_event("blog-agent/run.resume", {"run_id": run_id, "human_response": human_response})
