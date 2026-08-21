import threading
import time

import pytest

from services.groq_admission import (
    GroqAdmissionController,
    invoke_with_groq_admission,
)


def create_controller(
    *,
    max_concurrent_generations=2,
    token_budget_per_minute=8000,
    token_budget_safety_margin=0.25,
    reservation_tokens=1000,
):
    return GroqAdmissionController(
        max_concurrent_generations=(max_concurrent_generations),
        token_budget_per_minute=(token_budget_per_minute),
        token_budget_safety_margin=(token_budget_safety_margin),
        reservation_tokens=reservation_tokens,
    )


def test_simultaneous_admissions_respect_concurrency_limit():
    controller = create_controller(
        max_concurrent_generations=1,
    )

    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first_request():
        with controller.generation():
            first_entered.set()
            release_first.wait(timeout=2)

    def second_request():
        first_entered.wait(timeout=2)

        with controller.generation():
            second_entered.set()

    first = threading.Thread(
        target=first_request,
    )
    second = threading.Thread(
        target=second_request,
    )

    first.start()
    second.start()

    assert first_entered.wait(timeout=1)

    time.sleep(0.1)

    assert second_entered.is_set() is False

    release_first.set()

    assert second_entered.wait(timeout=1)

    first.join(timeout=1)
    second.join(timeout=1)

    assert first.is_alive() is False
    assert second.is_alive() is False


def test_budget_gate_waits_until_previous_reservation_expires():
    now = [0.0]
    sleeps = []

    def clock():
        return now[0]

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    controller = GroqAdmissionController(
        max_concurrent_generations=2,
        token_budget_per_minute=1000,
        token_budget_safety_margin=0.0,
        reservation_tokens=600,
        clock=clock,
        sleep=sleep,
    )

    with controller.generation():
        pass

    with controller.generation():
        pass

    assert sleeps == [60.0]


def test_exception_releases_concurrency_slot():
    controller = create_controller(
        max_concurrent_generations=1,
    )

    with pytest.raises(RuntimeError):
        with controller.generation():
            raise RuntimeError("provider failed")

    acquired = threading.Event()

    def next_request():
        with controller.generation():
            acquired.set()

    thread = threading.Thread(
        target=next_request,
    )

    thread.start()

    assert acquired.wait(timeout=1)

    thread.join(timeout=1)

    assert thread.is_alive() is False


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

    def __init__(self, headers):
        self.response = FakeResponse(headers)


class FailingRunnable:
    def invoke(self, input):
        raise FakeRateLimitError(
            {
                "retry-after": "5",
            }
        )


class SuccessfulRunnable:
    def __init__(self):
        self.called = False

    def invoke(self, input):
        self.called = True
        return "ok"


def test_rate_limit_cooldown_blocks_next_admission():
    now = [0.0]
    sleeps = []

    def clock():
        return now[0]

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    controller = GroqAdmissionController(
        max_concurrent_generations=1,
        token_budget_per_minute=8000,
        token_budget_safety_margin=0.0,
        reservation_tokens=100,
        clock=clock,
        sleep=sleep,
    )

    with pytest.raises(FakeRateLimitError):
        invoke_with_groq_admission(
            controller=controller,
            runnable=FailingRunnable(),
            input="first",
        )

    runnable = SuccessfulRunnable()

    result = invoke_with_groq_admission(
        controller=controller,
        runnable=runnable,
        input="second",
    )

    assert result == "ok"
    assert runnable.called is True
    assert sleeps == [5.0]


def test_non_groq_work_is_not_wrapped_or_delayed():
    runnable = SuccessfulRunnable()

    assert runnable.invoke("gemini-work") == "ok"

    assert runnable.called is True


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        create_controller(
            max_concurrent_generations=0,
        )

    with pytest.raises(ValueError):
        create_controller(
            token_budget_per_minute=0,
        )

    with pytest.raises(ValueError):
        create_controller(
            token_budget_safety_margin=1.0,
        )

    with pytest.raises(ValueError):
        create_controller(
            reservation_tokens=0,
        )
