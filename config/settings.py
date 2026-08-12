import os

import groq
from dotenv import load_dotenv
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.types import RetryPolicy

load_dotenv()


rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.33,
    check_every_n_seconds=0.1,
    max_bucket_size=2,
)


groq_retry_policy = RetryPolicy(
    max_attempts=6,
    initial_interval=3.0,
    backoff_factor=2.0,
    max_interval=30.0,
    jitter=True,
    retry_on=[groq.RateLimitError],
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
