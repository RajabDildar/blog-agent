import operator
from typing import Annotated, TypedDict

from schemas.models import (
    EditorialIssue,
    EditorialReview,
    Plan,
    ResearchEvidence,
    SectionOutput,
)


class State(TypedDict):
    run_id: str
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

    citation_issues: list[EditorialIssue]

    editorial_review: EditorialReview | None
    revision_count: int

    image_specs: list[dict]
    image_results: list[dict]

    final: str

    # Article validation.
    article_validation_errors: list[str]
    article_validation_passed: bool
    article_repair_count: int

    # Final artifact validation.
    final_validation_errors: list[str]
    final_validation_passed: bool

    saved_path: str
