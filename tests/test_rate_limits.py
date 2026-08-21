from types import SimpleNamespace

from services.rate_limits import (
    extract_rate_limit_info,
    get_provider_retry_delay_seconds,
    is_rate_limit_error,
)


class FakeHeaders:
    def __init__(self, values):
        self._values = values

    def items(self):
        return self._values.items()


class FakeResponse:
    def __init__(self, headers):
        self.headers = FakeHeaders(headers)


class FakeRateLimitError(Exception):
    status_code = 429

    def __init__(self, headers=None):
        self.response = FakeResponse(headers or {})


class FakeProviderError(Exception):
    status_code = 500


def test_structured_rate_limit_metadata_is_extracted():
    exc = FakeRateLimitError(
        {
            "retry-after": "2",
            "x-ratelimit-reset-tokens": "7.66s",
            "x-ratelimit-remaining-tokens": "0",
            "x-ratelimit-limit-tokens": "8000",
        }
    )

    assert is_rate_limit_error(exc) is True

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert info.provider == "groq"
    assert info.status_code == 429
    assert info.retry_after_seconds == 2.0
    assert info.reset_tokens_seconds == 7.66
    assert info.remaining_tokens == 0
    assert info.limit_tokens == 8000


def test_retry_after_takes_precedence_as_metadata():
    exc = FakeRateLimitError(
        {
            "retry-after": "2",
            "x-ratelimit-reset-tokens": "7.66s",
        }
    )

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert info.retry_after_seconds == 2.0
    assert info.reset_tokens_seconds == 7.66


def test_duration_headers_support_minutes_and_seconds():
    exc = FakeRateLimitError(
        {
            "retry-after": "2m59.56s",
        }
    )

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert info.retry_after_seconds == 179.56


def test_missing_headers_do_not_crash():
    exc = FakeRateLimitError()

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert info.provider == "groq"
    assert info.status_code == 429
    assert info.retry_after_seconds is None
    assert info.reset_tokens_seconds is None
    assert info.remaining_tokens is None
    assert info.limit_tokens is None


def test_malformed_timing_values_are_ignored():
    exc = FakeRateLimitError(
        {
            "retry-after": "not-a-duration",
            "x-ratelimit-reset-tokens": "-10",
            "x-ratelimit-remaining-tokens": "unknown",
            "x-ratelimit-limit-tokens": "invalid",
        }
    )

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert info.retry_after_seconds is None
    assert info.reset_tokens_seconds is None
    assert info.remaining_tokens is None
    assert info.limit_tokens is None


def test_non_rate_limit_error_is_not_classified():
    exc = FakeProviderError()

    assert is_rate_limit_error(exc) is False
    assert extract_rate_limit_info(exc) is None


def test_missing_response_object_is_safe():
    exc = SimpleNamespace(status_code=429)

    assert is_rate_limit_error(exc) is True

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert info.provider == "groq"
    assert info.status_code == 429
    assert info.retry_after_seconds is None


def test_provider_retry_delay_prefers_retry_after():
    exc = FakeRateLimitError(
        {
            "retry-after": "2",
            "x-ratelimit-reset-tokens": "7.66s",
        }
    )

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert get_provider_retry_delay_seconds(info) == 2.0


def test_provider_retry_delay_falls_back_to_token_reset():
    exc = FakeRateLimitError(
        {
            "x-ratelimit-reset-tokens": "7.66s",
        }
    )

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert get_provider_retry_delay_seconds(info) == 7.66


def test_invalid_retry_after_does_not_override_valid_token_reset():
    exc = FakeRateLimitError(
        {
            "retry-after": "not-a-duration",
            "x-ratelimit-reset-tokens": "7.66s",
        }
    )

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert info.retry_after_seconds is None
    assert info.reset_tokens_seconds == 7.66
    assert get_provider_retry_delay_seconds(info) == 7.66


def test_invalid_provider_timing_returns_no_delay():
    exc = FakeRateLimitError(
        {
            "retry-after": "invalid",
            "x-ratelimit-reset-tokens": "also-invalid",
        }
    )

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert get_provider_retry_delay_seconds(info) is None


def test_provider_retry_delay_returns_none_when_metadata_is_missing():
    exc = FakeRateLimitError()

    info = extract_rate_limit_info(exc)

    assert info is not None
    assert get_provider_retry_delay_seconds(info) is None


def test_provider_retry_delay_requires_rate_limit_metadata():
    exc = FakeProviderError()

    assert is_rate_limit_error(exc) is False
    assert extract_rate_limit_info(exc) is None
