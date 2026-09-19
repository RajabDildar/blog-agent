from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


FreshnessStatus = Literal[
    "fresh",
    "stale_warning",
    "unknown",
    "exempt_authoritative_spec",
]


def support_strength_score(
    support_strength: SupportStrength,
) -> float:
    return {
        "direct": 1.0,
        "indirect": 0.6,
        "weak": 0.3,
    }[support_strength]


OFFICIAL_PRIMARY_SOURCE_TYPES: frozenset[SourceType] = frozenset({
    "official_documentation",
    "government_source",
    "academic_paper",
    "official_company_announcement",
    "standards_document",
})


EXEMPT_AUTHORITATIVE_SOURCE_TYPES: frozenset[SourceType] = frozenset({
    "official_documentation",
    "standards_document",
    "academic_paper",
    "github_repository",
    "reputable_industry_source",
})


class ExtractedResearchEvidence(BaseModel):
    claim: str
    source_title: str
    url: str
    supporting_text: str = ""
    relevance: str = ""
    support_strength: SupportStrength = "weak"
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )


class ExtractedResearchPack(BaseModel):
    evidence: list[ExtractedResearchEvidence] = Field(default_factory=list)
    research_brief: str = ""


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
    freshness_status: FreshnessStatus = "unknown"
    freshness_warning: str = ""

    tavily_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

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

    quality_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Informational LLM extraction quality score. Not used as hard rejection gate.",
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


class IntentAnalysis(BaseModel):
    outcome: Literal[
        "accepted",
        "needs_clarification",
        "blocked",
        "invalid",
    ]

    normalized_topic: str = ""

    block_category: Literal[
        "",
        "explicit_sexual",
        "graphic_violence",
        "self_harm_instructions",
        "illegal_wrongdoing",
        "cyber_abuse",
        "privacy_abuse",
        "hate_or_extremist_advocacy",
    ] = ""

    invalid_reason: Literal[
        "",
        "nonsense",
        "not_a_blog_request",
        "out_of_scope_non_technical",
        "insufficient_information",
    ] = ""

    user_message: str = ""
    clarification_question: str = ""
    clarification_options: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome_fields(self) -> "IntentAnalysis":
        if self.outcome == "accepted":
            if not self.normalized_topic or not self.normalized_topic.strip():
                raise ValueError("accepted outcome requires non-empty normalized_topic")
        elif self.outcome == "needs_clarification":
            if not self.clarification_question or not self.clarification_question.strip():
                raise ValueError("needs_clarification outcome requires clarification_question")
            if len(self.clarification_options) != 3:
                raise ValueError("needs_clarification outcome requires exactly 3 clarification_options")
            stripped_options = [opt.strip() for opt in self.clarification_options]
            if any(not opt for opt in stripped_options):
                raise ValueError("clarification_options must be non-empty strings")
            if len(set(stripped_options)) != 3:
                raise ValueError("clarification_options must be distinct")
        elif self.outcome == "blocked":
            if not self.block_category:
                raise ValueError("blocked outcome requires a supported block_category")
            if not self.user_message or not self.user_message.strip():
                raise ValueError("blocked outcome requires a safe user_message")
        elif self.outcome == "invalid":
            if not self.invalid_reason:
                raise ValueError("invalid outcome requires invalid_reason")
            if not self.user_message or not self.user_message.strip():
                raise ValueError("invalid outcome requires user_message")
        return self


class IntentHumanResponse(BaseModel):
    action: Literal[
        "select_option",
        "custom_input",
        "proceed",
        "cancel",
    ]
    value: str = ""

    @model_validator(mode="after")
    def validate_action(self) -> "IntentHumanResponse":
        if self.action in ("select_option", "custom_input"):
            if not self.value or not self.value.strip():
                raise ValueError(f"{self.action} requires non-empty value")
        return self


class ProposedTopicAnalysis(BaseModel):
    proposed_topic: str = Field(..., min_length=3)

