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


class EvaluationRun(BaseModel):
    topic: str

    run_id: str

    status: str

    article_path: str | None = None

    evaluation: EvaluationResult | None = None

    metrics: EvaluationMetrics

    failure: str | None = None
