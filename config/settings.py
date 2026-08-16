import os

import groq
import httpx
from dotenv import load_dotenv
from google.genai import errors as genai_errors
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.types import RetryPolicy

load_dotenv()


rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.33,
    check_every_n_seconds=0.1,
    max_bucket_size=2,
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

    # Groq
    if isinstance(
        exc,
        (
            groq.RateLimitError,
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
    max_attempts=4,
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

MAX_EDITORIAL_REVISIONS = 1
MAX_ARTICLE_REPAIRS = 1
