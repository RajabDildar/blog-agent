from datetime import datetime

from pydantic import BaseModel, Field


class EvaluationScores(BaseModel):
    overall_quality: int = Field(
        ...,
        ge=1,
        le=10,
    )

    structure: int = Field(
        ...,
        ge=1,
        le=10,
    )

    technical_accuracy: int = Field(
        ...,
        ge=1,
        le=10,
    )

    research_quality: int = Field(
        ...,
        ge=1,
        le=10,
    )

    coherence: int = Field(
        ...,
        ge=1,
        le=10,
    )

    usefulness: int = Field(
        ...,
        ge=1,
        le=10,
    )

    writing_quality: int = Field(
        ...,
        ge=1,
        le=10,
    )

    citations: int = Field(
        ...,
        ge=1,
        le=10,
    )

    images: int = Field(
        ...,
        ge=1,
        le=10,
    )


class EvaluationResult(BaseModel):
    scores: EvaluationScores

    strengths: list[str] = Field(
        default_factory=list,
        max_length=5,
    )

    weaknesses: list[str] = Field(
        default_factory=list,
        max_length=5,
    )

    summary: str


class EvaluationMetrics(BaseModel):
    llm_calls: int = Field(
        ...,
        ge=0,
    )

    research_calls: int = Field(
        ...,
        ge=0,
    )

    image_calls: int = Field(
        ...,
        ge=0,
    )

    revision_count: int = Field(
        ...,
        ge=0,
    )

    generation_time_seconds: float = Field(
        ...,
        ge=0,
    )

    retries: int = Field(
        ...,
        ge=0,
    )

    node_attempts: int = Field(default=0, ge=0)
    judge_calls: int = Field(default=0, ge=0)
    citation_issue_counts: dict[str, int] = Field(default_factory=dict)

    official_source_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    unknown_source_ratio: float = Field(default=0.0, ge=0.0, le=1.0)

    average_authority_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    average_quality_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    weak_source_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    unique_domain_count: int = Field(
        default=0,
        ge=0,
    )

    source_type_distribution: dict[str, int] = Field(
        default_factory=dict,
    )

    authority_distribution: dict[str, int] = Field(default_factory=dict)


class EvaluationRun(BaseModel):
    topic: str

    run_id: str

    status: str

    article_path: str | None = None

    evaluation: EvaluationResult | None = None

    metrics: EvaluationMetrics

    failure: str | None = None

    rate_limit_recoveries: int = Field(
        default=0,
        ge=0,
    )

    rate_limit_wait_seconds: float = Field(
        default=0,
        ge=0,
    )

    article_artifact: str | None = None
    diagnostics_artifact: str | None = None
    citation_issues: list[dict] = Field(default_factory=list)


class EvaluationManifest(BaseModel):
    experiment_name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    pipeline_commit: str
    pipeline_dirty: bool
    started_at: datetime
    finished_at: datetime | None = None
    seed_topics_path: str
    seed_topics_sha256: str
    writer_model: str
    revision_model: str
    pipeline_gemini_model: str
    judge_model: str
    judge_image_input: bool
    phase8_settings: dict[str, str | int | float | bool]
    python_version: str
    locked_package_versions: dict[str, str]
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
