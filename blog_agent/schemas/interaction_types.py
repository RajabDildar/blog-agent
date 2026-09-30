"""Interaction type definitions for human-in-the-loop graph interrupts."""

from enum import Enum


class InteractionType(str, Enum):
    """Enumeration of standard interaction type strings produced by LangGraph interrupts."""

    CLARIFICATION_REQUIRED = "clarification_required"
    TOPIC_CONFIRMATION_REQUIRED = "topic_confirmation_required"
