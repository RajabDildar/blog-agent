from typing import TypedDict

from schemas.models import (
    EditorialReview,
    Plan,
    ResearchEvidence,
    SectionOutput,
)


class State(TypedDict):
    topic: str

    mode: str
    needs_research: bool
    queries: list[str]
    research_focus: list[str]

    evidence: list[ResearchEvidence]
    research_brief: str

    plan: Plan | None

    sections: dict[int, SectionOutput]

    merged_md: str

    editorial_review: EditorialReview | None
    revision_count: int

    image_specs: list[dict]

    final: str
