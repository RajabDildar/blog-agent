import groq
import httpx
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from config.settings import provider_retry_policy


class RetryState(TypedDict):
    attempts: int


def make_rate_limit_error() -> groq.RateLimitError:
    request = httpx.Request(
        "POST",
        "https://api.groq.com/openai/v1/chat/completions",
    )

    response = httpx.Response(
        429,
        request=request,
    )

    return groq.RateLimitError(
        "rate limited",
        response=response,
        body=None,
    )


def test_langgraph_retries_transient_provider_error():
    attempts = 0

    def flaky_node(state: RetryState):
        nonlocal attempts

        attempts += 1

        if attempts < 3:
            raise make_rate_limit_error()

        return {
            "attempts": attempts,
        }

    builder = StateGraph(RetryState)

    builder.add_node(
        "flaky",
        flaky_node,
        retry_policy=provider_retry_policy,
    )

    builder.add_edge(
        START,
        "flaky",
    )

    builder.add_edge(
        "flaky",
        END,
    )

    graph = builder.compile()

    result = graph.invoke(
        {
            "attempts": 0,
        }
    )

    assert result["attempts"] == 3
    assert attempts == 3


def test_langgraph_does_not_retry_non_transient_error():
    attempts = 0

    def broken_node(state: RetryState):
        nonlocal attempts

        attempts += 1

        raise ValueError("invalid generated data")

    builder = StateGraph(RetryState)

    builder.add_node(
        "broken",
        broken_node,
        retry_policy=provider_retry_policy,
    )

    builder.add_edge(
        START,
        "broken",
    )

    builder.add_edge(
        "broken",
        END,
    )

    graph = builder.compile()

    try:
        graph.invoke(
            {
                "attempts": 0,
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")

    assert attempts == 1
