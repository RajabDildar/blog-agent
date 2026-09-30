"""Inngest client configuration and event emission utilities."""

from __future__ import annotations

import logging
from typing import Any

import inngest

from apps.api.config import get_settings

logger = logging.getLogger("blog_agent.inngest")
settings = get_settings()


def create_inngest_client() -> inngest.Inngest:
    """Initializes the Inngest client according to environment configuration."""
    kwargs: dict[str, Any] = {
        "app_id": settings.INNGEST_APP_ID,
        "is_production": settings.is_production,
    }
    if settings.INNGEST_EVENT_KEY:
        kwargs["event_key"] = settings.INNGEST_EVENT_KEY
    if settings.INNGEST_SIGNING_KEY:
        kwargs["signing_key"] = settings.INNGEST_SIGNING_KEY

    return inngest.Inngest(**kwargs)


inngest_client = create_inngest_client()


def send_inngest_event(name: str, data: dict[str, Any]) -> list[str]:
    """
    Synchronously dispatches an event to Inngest with identifier payload.
    Catches and logs connection errors in dev/testing environments without crashing requests.
    """
    event = inngest.Event(name=name, data=data)
    try:
        return inngest_client.send_sync(event)
    except Exception as exc:  # noqa: BLE001 - Dev/test dispatch failures degrade to an empty result.
        logger.warning(f"Could not send Inngest event '{name}': {exc}")
        return []
