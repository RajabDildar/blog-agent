from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

try:
    from groq import RateLimitError
except ImportError:
    RateLimitError = None


@dataclass(frozen=True)
class RateLimitInfo:
    provider: str
    status_code: int | None
    retry_after_seconds: float | None
    reset_tokens_seconds: float | None
    remaining_tokens: int | None
    limit_tokens: int | None


_DURATION_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)m)?"
    r"\s*"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)s)?"
    r"\s*$"
)


def _get_headers(exc: Exception) -> Mapping[str, str]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)

    if headers is None:
        return {}

    try:
        return {str(key).lower(): str(value) for key, value in headers.items()}
    except AttributeError, TypeError:
        return {}


def _parse_non_negative_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        parsed = float(str(value).strip())
    except TypeError, ValueError:
        return None

    if parsed < 0:
        return None

    return parsed


def _parse_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        parsed = int(str(value).strip())
    except TypeError, ValueError:
        return None

    if parsed < 0:
        return None

    return parsed


def _parse_duration_seconds(value: Any) -> float | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    direct_seconds = _parse_non_negative_float(text)
    if direct_seconds is not None:
        return direct_seconds

    match = _DURATION_PATTERN.fullmatch(text)
    if match is None:
        return None

    minutes = match.group("minutes")
    seconds = match.group("seconds")

    if minutes is None and seconds is None:
        return None

    total = 0.0

    if minutes is not None:
        total += float(minutes) * 60.0

    if seconds is not None:
        total += float(seconds)

    return total


def is_rate_limit_error(exc: Exception) -> bool:
    if RateLimitError is not None and isinstance(exc, RateLimitError):
        return True

    status_code = getattr(exc, "status_code", None)

    try:
        return int(status_code) == 429
    except TypeError, ValueError:
        return False


def extract_rate_limit_info(exc: Exception) -> RateLimitInfo | None:
    if not is_rate_limit_error(exc):
        return None

    headers = _get_headers(exc)

    status_code = getattr(exc, "status_code", None)
    try:
        normalized_status_code = int(status_code)
    except TypeError, ValueError:
        normalized_status_code = 429

    return RateLimitInfo(
        provider="groq",
        status_code=normalized_status_code,
        retry_after_seconds=_parse_duration_seconds(headers.get("retry-after")),
        reset_tokens_seconds=_parse_duration_seconds(
            headers.get("x-ratelimit-reset-tokens")
        ),
        remaining_tokens=_parse_non_negative_int(
            headers.get("x-ratelimit-remaining-tokens")
        ),
        limit_tokens=_parse_non_negative_int(headers.get("x-ratelimit-limit-tokens")),
    )
