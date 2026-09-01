import os

import groq
import httpx
from dotenv import load_dotenv
from google.genai import errors as genai_errors
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.types import RetryPolicy

from services.groq_admission import (
    GroqAdmissionController,
)
from services.rate_limits import (
    extract_rate_limit_info,
    get_provider_retry_delay_seconds,
    is_rate_limit_error,
)

load_dotenv()


RATE_LIMIT_SHORT_WAIT_SECONDS = float(
    os.getenv(
        "RATE_LIMIT_SHORT_WAIT_SECONDS",
        "10",
    )
)

EVAL_MAX_RATE_LIMIT_WAIT_SECONDS = float(
    os.getenv(
        "EVAL_MAX_RATE_LIMIT_WAIT_SECONDS",
        "120",
    )
)

EVAL_BETWEEN_RUN_DELAY_SECONDS = float(
    os.getenv(
        "EVAL_BETWEEN_RUN_DELAY_SECONDS",
        "5",
    )
)

EVAL_RESUME_ATTEMPT_LIMIT = int(
    os.getenv(
        "EVAL_RESUME_ATTEMPT_LIMIT",
        "3",
    )
)

TAVILY_MIN_RELEVANCE_SCORE = float(
    os.getenv(
        "TAVILY_MIN_RELEVANCE_SCORE",
        "0.3",
    )
)

TAVILY_MAX_RESULTS_PER_DOMAIN = int(
    os.getenv(
        "TAVILY_MAX_RESULTS_PER_DOMAIN",
        "2",
    )
)

WEAK_SOURCE_AUTHORITY_THRESHOLD = float(
    os.getenv(
        "WEAK_SOURCE_AUTHORITY_THRESHOLD",
        "0.5",
    )
)

GROQ_MAX_CONCURRENT_GENERATIONS = int(
    os.getenv(
        "GROQ_MAX_CONCURRENT_GENERATIONS",
        "2",
    )
)

GROQ_TOKEN_BUDGET_PER_MINUTE = int(
    os.getenv(
        "GROQ_TOKEN_BUDGET_PER_MINUTE",
        "8000",
    )
)

GROQ_TOKEN_BUDGET_SAFETY_MARGIN = float(
    os.getenv(
        "GROQ_TOKEN_BUDGET_SAFETY_MARGIN",
        "0.25",
    )
)

GROQ_TOKEN_RESERVATION_PER_GENERATION = int(
    os.getenv(
        "GROQ_TOKEN_RESERVATION_PER_GENERATION",
        "1500",
    )
)

PROVIDER_RETRY_MAX_ATTEMPTS = 4

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.33,
    check_every_n_seconds=0.1,
    max_bucket_size=2,
)

groq_admission_controller = GroqAdmissionController(
    max_concurrent_generations=(GROQ_MAX_CONCURRENT_GENERATIONS),
    token_budget_per_minute=(GROQ_TOKEN_BUDGET_PER_MINUTE),
    token_budget_safety_margin=(GROQ_TOKEN_BUDGET_SAFETY_MARGIN),
    reservation_tokens=(GROQ_TOKEN_RESERVATION_PER_GENERATION),
)


TRANSIENT_HTTP_STATUS_CODES = {
    408,
    409,
    429,
    500,
    502,
    503,
    504,
}


def is_transient_provider_error(
    exc: Exception,
) -> bool:
    """Return True only for provider failures worth retrying."""

    # Groq rate limits require provider-aware classification.
    if is_rate_limit_error(exc):
        info = extract_rate_limit_info(exc)

        if info is None:
            return True

        delay = get_provider_retry_delay_seconds(info)

        # No usable provider timing: retain the existing
        # bounded retry fallback.
        if delay is None:
            return True

        return delay <= RATE_LIMIT_SHORT_WAIT_SECONDS

    # Groq non-rate-limit transient failures.
    if isinstance(
        exc,
        (
            groq.APIConnectionError,
            groq.APITimeoutError,
            groq.InternalServerError,
        ),
    ):
        return True

    # Gemini / google-genai
    if isinstance(
        exc,
        genai_errors.ServerError,
    ):
        return True

    if isinstance(
        exc,
        genai_errors.ClientError,
    ):
        return (
            getattr(
                exc,
                "code",
                None,
            )
            in TRANSIENT_HTTP_STATUS_CODES
        )

    # Generic transport failures
    if isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.TimeoutException,
        ),
    ):
        return True

    # Generic HTTP/provider errors
    status_code = getattr(
        exc,
        "status_code",
        None,
    )

    if status_code in TRANSIENT_HTTP_STATUS_CODES:
        return True

    code = getattr(
        exc,
        "code",
        None,
    )

    return code in TRANSIENT_HTTP_STATUS_CODES


provider_retry_policy = RetryPolicy(
    max_attempts=PROVIDER_RETRY_MAX_ATTEMPTS,
    initial_interval=2.0,
    backoff_factor=2.0,
    max_interval=20.0,
    jitter=True,
    retry_on=is_transient_provider_error,
)


WRITER_MODEL = os.getenv(
    "GROQ_WRITER_MODEL",
    "llama-3.3-70b-versatile",
)

REVISION_MODEL = os.getenv(
    "GROQ_REVISION_MODEL",
    "llama-3.3-70b-versatile",
)

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.1-flash-lite",
)

EVAL_JUDGE_MODEL = os.getenv(
    "EVAL_JUDGE_MODEL",
    "gemini-3.1-flash-lite",
)

CHECKPOINT_SQLITE_PATH = os.getenv(
    "CHECKPOINT_SQLITE_PATH",
    "runs/checkpoints.sqlite",
)

MAX_EDITORIAL_REVISIONS = 1
MAX_ARTICLE_REPAIRS = 1

EVAL_JUDGE_IMAGE_INPUT = True
