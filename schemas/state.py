import operator

from typing import Annotated, TypedDict

from schemas.models import EvidenceItem, Plan


class State(TypedDict):
    topic: str

    # routing / research
    mode: str
    needs_research: bool
    queries: list[str]
    evidence: list[EvidenceItem]
    plan: Plan | None

    # workers
    sections: Annotated[
        list[tuple[int, str]],
        operator.add,
    ]

    # reducer/image
    merged_md: str
    md_with_placeholders: str
    image_specs: list[dict]

    final: str
