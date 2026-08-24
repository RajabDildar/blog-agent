from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal[
    "official_documentation",
    "government_source",
    "academic_paper",
    "official_company_announcement",
    "github_repository",
    "standards_document",
    "reputable_industry_source",
    "vendor_blog",
    "unknown",
]


SupportStrength = Literal[
    "direct",
    "indirect",
    "weak",
]


class Task(BaseModel):
    id: int
    title: str

    goal: str = Field(
        ...,
        description="What the reader should understand or accomplish.",
    )

    bullets: list[str] = Field(
        ...,
        min_length=3,
        max_length=6,
    )

    target_words: int = Field(
        ...,
        ge=100,
        le=700,
    )

    section_role: Literal[
        "introduction",
        "concept",
        "comparison",
        "implementation",
        "example",
        "architecture",
        "limitations",
        "security",
        "performance",
        "conclusion",
        "other",
    ] = "other"

    tags: list[str] = Field(default_factory=list)

    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False

    evidence_refs: list[int] = Field(default_factory=list)

    must_avoid: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    blog_title: str

    thesis: str
    opening_angle: str
    reader_promise: str

    audience: str
    tone: str

    blog_kind: Literal[
        "explainer",
        "tutorial",
        "news_roundup",
        "comparison",
        "system_design",
    ] = "explainer"

    constraints: list[str] = Field(default_factory=list)

    key_takeaways: list[str] = Field(
        default_factory=list,
        max_length=5,
    )

    tasks: list[Task]


class ResearchEvidence(BaseModel):
    id: int

    claim: str
    source_title: str
    url: str

    supporting_text: str = ""
    relevance: str = ""

    published_at: str | None = None

    source_type: SourceType = "unknown"

    authority_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    support_strength: SupportStrength = "weak"

    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )


class ResearchPack(BaseModel):
    evidence: list[ResearchEvidence] = Field(default_factory=list)

    research_brief: str = ""


class RouterDecision(BaseModel):
    needs_research: bool

    mode: Literal[
        "closed_book",
        "hybrid",
        "open_book",
    ]

    research_focus: list[str] = Field(default_factory=list)

    queries: list[str] = Field(
        default_factory=list,
        max_length=8,
    )


class SectionOutput(BaseModel):
    body_markdown: str


class EditorialIssue(BaseModel):
    task_id: int | None = None

    category: Literal[
        "factual",
        "unsupported_claim",
        "repetition",
        "coherence",
        "style",
        "code",
        "citation",
        "structure",
    ]

    severity: Literal[
        "low",
        "medium",
        "high",
    ]

    problem: str
    correction: str


class EditorialReview(BaseModel):
    approved: bool

    overall_score: int = Field(
        ge=1,
        le=10,
    )

    issues: list[EditorialIssue] = Field(default_factory=list)

    sections_to_revise: list[int] = Field(default_factory=list)


class ImageSpec(BaseModel):
    id: str

    section_id: int

    image_type: Literal[
        "technical_diagram",
        "conceptual",
        "illustration",
    ]

    purpose: str

    visual_description: str = Field(
        ...,
        min_length=20,
        max_length=500,
    )

    key_elements: list[str] = Field(
        default_factory=list,
        min_length=1,
        max_length=8,
    )

    placement: Literal[
        "start",
        "middle",
        "end",
    ]

    alt: str = Field(
        ...,
        min_length=3,
        max_length=160,
    )

    caption: str = Field(
        ...,
        min_length=3,
        max_length=240,
    )


class GlobalImagePlan(BaseModel):
    images: list[ImageSpec] = Field(
        default_factory=list,
        max_length=3,
    )


class MarkdownRepairOutput(BaseModel):
    markdown: str
