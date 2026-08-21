from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass

from services.rate_limits import (
    extract_rate_limit_info,
    get_provider_retry_delay_seconds,
    is_rate_limit_error,
)


@dataclass(frozen=True)
class _Reservation:
    created_at: float
    tokens: int


class GroqAdmissionController:
    """Local single-process admission control for shared Groq quota."""

    def __init__(
        self,
        *,
        max_concurrent_generations: int,
        token_budget_per_minute: int,
        token_budget_safety_margin: float,
        reservation_tokens: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_concurrent_generations < 1:
            raise ValueError("max_concurrent_generations must be at least 1.")

        if token_budget_per_minute < 1:
            raise ValueError("token_budget_per_minute must be at least 1.")

        if not 0 <= token_budget_safety_margin < 1:
            raise ValueError("token_budget_safety_margin must be >= 0 and < 1.")

        if reservation_tokens < 1:
            raise ValueError("reservation_tokens must be at least 1.")

        self._max_concurrent_generations = max_concurrent_generations
        self._reservation_tokens = reservation_tokens
        self._effective_budget = max(
            1,
            int(token_budget_per_minute * (1 - token_budget_safety_margin)),
        )

        self._clock = clock
        self._sleep = sleep
        self._condition = threading.Condition()

        self._active_generations = 0
        self._reservations: deque[_Reservation] = deque()
        self._cooldown_until: float | None = None

    def _expire_reservations(
        self,
        now: float,
    ) -> None:
        cutoff = now - 60.0

        while self._reservations and self._reservations[0].created_at <= cutoff:
            self._reservations.popleft()

    def _reserved_tokens(self) -> int:
        return sum(reservation.tokens for reservation in self._reservations)

    def _wait_seconds(
        self,
        now: float,
    ) -> float:
        self._expire_reservations(now)

        waits: list[float] = []

        if self._cooldown_until is not None and now < self._cooldown_until:
            waits.append(self._cooldown_until - now)

        if self._active_generations >= self._max_concurrent_generations:
            waits.append(0.05)

        if self._reserved_tokens() + self._reservation_tokens > self._effective_budget:
            if self._reservations:
                oldest = self._reservations[0]

                waits.append(
                    max(
                        0.0,
                        oldest.created_at + 60.0 - now,
                    )
                )
            else:
                waits.append(0.05)

        if not waits:
            return 0.0

        return max(waits)

    def acquire(self) -> None:
        while True:
            with self._condition:
                now = self._clock()

                wait_seconds = self._wait_seconds(now)

                if wait_seconds <= 0:
                    self._active_generations += 1
                    self._reservations.append(
                        _Reservation(
                            created_at=now,
                            tokens=self._reservation_tokens,
                        )
                    )
                    return

            self._sleep(wait_seconds)

    def release(self) -> None:
        with self._condition:
            if self._active_generations < 1:
                raise RuntimeError(
                    "Groq admission release called without an active generation."
                )

            self._active_generations -= 1
            self._condition.notify_all()

    def record_rate_limit(
        self,
        exc: Exception,
    ) -> None:
        if not is_rate_limit_error(exc):
            return

        info = extract_rate_limit_info(exc)

        if info is None:
            return

        delay = get_provider_retry_delay_seconds(info)

        if delay is None:
            return

        with self._condition:
            cooldown_until = self._clock() + delay

            if self._cooldown_until is None or cooldown_until > self._cooldown_until:
                self._cooldown_until = cooldown_until

            self._condition.notify_all()

    @contextmanager
    def generation(self):
        self.acquire()

        try:
            yield
        finally:
            self.release()


def invoke_with_groq_admission(
    *,
    controller: GroqAdmissionController,
    runnable,
    input,
):
    with controller.generation():
        try:
            return runnable.invoke(input)
        except Exception as exc:
            controller.record_rate_limit(exc)
            raise
