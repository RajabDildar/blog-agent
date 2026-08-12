import operator
from typing import Annotated, TypedDict

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

    sections: Annotated[
        dict[int, SectionOutput],
        operator.or_,
    ]

    merged_md: str

    editorial_review: EditorialReview | None
    revision_count: int

    image_specs: list[dict]
    image_results: list[dict]

    final: str

    validation_errors: list[str]
    validation_passed: bool
    repair_count: int

    saved_path: str
