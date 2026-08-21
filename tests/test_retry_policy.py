from types import SimpleNamespace

from config.settings import (
    RATE_LIMIT_SHORT_WAIT_SECONDS,
    is_transient_provider_error,
)
from services.rate_limits import (
    extract_rate_limit_info,
    get_provider_retry_delay_seconds,
)


class FakeRateLimitError(Exception):
    status_code = 429

    def __init__(self, headers=None):
        self.response = SimpleNamespace(
            headers=headers or {},
        )


class FakeProviderError(Exception):
    status_code = 500


def test_short_rate_limit_is_retryable():
    exc = FakeRateLimitError(
        {
            "retry-after": "2",
        }
    )

    assert (
        get_provider_retry_delay_seconds(
            extract_rate_limit_info(exc),
        )
        == 2.0
    )

    assert is_transient_provider_error(exc) is True


def test_long_rate_limit_is_not_retryable():
    exc = FakeRateLimitError(
        {
            "retry-after": str(RATE_LIMIT_SHORT_WAIT_SECONDS + 1),
        }
    )

    assert is_transient_provider_error(exc) is False


def test_rate_limit_without_timing_uses_bounded_fallback():
    exc = FakeRateLimitError()

    assert is_transient_provider_error(exc) is True


def test_non_rate_limit_transient_error_remains_retryable():
    exc = FakeProviderError()

    assert is_transient_provider_error(exc) is True


def test_permanent_error_is_not_retryable():
    class BadRequestError(Exception):
        status_code = 400

    assert (
        is_transient_provider_error(
            BadRequestError(),
        )
        is False
    )
