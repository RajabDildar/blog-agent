import httpx
import groq
import pytest
from langgraph.types import RetryPolicy

from config.settings import (
    provider_retry_policy,
    is_transient_provider_error,
)


def make_groq_response(status_code: int) -> httpx.Response:
    request = httpx.Request(
        "POST",
        "https://api.groq.com/openai/v1/chat/completions",
    )

    return httpx.Response(
        status_code,
        request=request,
    )


def test_rate_limit_is_transient():
    exc = groq.RateLimitError(
        "rate limited",
        response=make_groq_response(429),
        body=None,
    )

    assert is_transient_provider_error(exc)


def test_connection_error_is_transient():
    assert is_transient_provider_error(groq.APIConnectionError(request=None)) is True


def test_timeout_is_transient():
    assert is_transient_provider_error(groq.APITimeoutError(request=None)) is True


def test_groq_server_error_is_transient():
    exc = groq.InternalServerError(
        "server error",
        response=make_groq_response(500),
        body=None,
    )

    assert is_transient_provider_error(exc)


@pytest.mark.parametrize(
    "status_code",
    [429, 500, 502, 503, 504],
)
def test_http_transient_status_is_transient(status_code):
    exc = Exception("provider error")
    exc.status_code = status_code

    assert is_transient_provider_error(exc) is True


@pytest.mark.parametrize(
    "status_code",
    [400, 401, 403, 404, 409, 422],
)
def test_non_transient_http_status_is_not_retryable(status_code):
    exc = Exception("client error")
    exc.status_code = status_code

    assert is_transient_provider_error(exc) is False


def test_value_error_is_not_retryable():
    assert is_transient_provider_error(ValueError("bad generated data")) is False


def test_runtime_error_is_not_retryable():
    assert is_transient_provider_error(RuntimeError("internal bug")) is False


def test_retry_policy_uses_transient_predicate():
    assert isinstance(provider_retry_policy, RetryPolicy)
    assert provider_retry_policy.max_attempts == 4
    assert provider_retry_policy.initial_interval == 2.0
    assert provider_retry_policy.backoff_factor == 2.0
    assert provider_retry_policy.max_interval == 20.0
    assert provider_retry_policy.jitter is True
    assert provider_retry_policy.retry_on is is_transient_provider_error
