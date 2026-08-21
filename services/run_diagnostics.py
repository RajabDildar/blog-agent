import json
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langgraph.runtime import get_runtime

from config.settings import (
    PROVIDER_RETRY_MAX_ATTEMPTS,
    RATE_LIMIT_SHORT_WAIT_SECONDS,
)
from services.rate_limits import (
    RateLimitInfo,
    RateLimitRetryExhausted,
    extract_rate_limit_info,
    get_provider_retry_delay_seconds,
)


class RunDiagnostics:
    def __init__(
        self,
        *,
        run_id: str,
        topic: str,
    ):
        self.run_id = run_id
        self.topic = topic
        self.started_at = time.time()

        self.status = "running"

        self.current_stage = ""
        self.current_provider: str | None = None

        self.retry_count = 0

        self.provider_attempts: dict[str, int] = defaultdict(int)

        self.markdown_deterministic_repairs = 0
        self.markdown_llm_repairs = 0

        self.editorial_reviews = 0
        self.editorial_revisions = 0

        self.image_attempts = 0
        self.image_ids: list[str] = []

        self.final_validation_failures = 0

        self.failure: dict[str, Any] | None = None

        self.events: list[dict[str, Any]] = []

        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return Path("runs") / self.run_id / "diagnostics.json"

    def _snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "topic": self.topic,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": (time.time() if self.status != "running" else None),
            "duration_seconds": round(
                time.time() - self.started_at,
                2,
            ),
            "current_stage": self.current_stage,
            "current_provider": self.current_provider,
            "retry_count": self.retry_count,
            "provider_attempts": dict(self.provider_attempts),
            "markdown": {
                "deterministic_repairs": (self.markdown_deterministic_repairs),
                "llm_repairs": (self.markdown_llm_repairs),
            },
            "editorial_reviews": (self.editorial_reviews),
            "editorial_revisions": (self.editorial_revisions),
            "image_attempts": (self.image_attempts),
            "image_ids": list(self.image_ids),
            "final_validation_failures": (self.final_validation_failures),
            "failure": self.failure,
            "events": list(self.events),
        }

    def _write(self) -> None:
        path = self.path

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                self._snapshot(),
                indent=2,
            ),
            encoding="utf-8",
        )

    def _record_event(
        self,
        *,
        event: str,
        **payload: Any,
    ) -> None:
        self.events.append(
            {
                "timestamp": time.time(),
                "event": event,
                **payload,
            }
        )

        self._write()

    def node_started(
        self,
        *,
        node: str,
        provider: str | None,
        attempt: int,
    ) -> None:
        with self._lock:
            self.current_stage = node
            self.current_provider = provider

            if provider:
                self.provider_attempts[provider] += 1

            if attempt > 1:
                self.retry_count += 1

            self._record_event(
                event="node_started",
                node=node,
                provider=provider,
                attempt=attempt,
            )

    def node_succeeded(
        self,
        *,
        node: str,
        provider: str | None,
        attempt: int,
    ) -> None:
        with self._lock:
            self.current_stage = node
            self.current_provider = provider

            self._record_event(
                event="node_succeeded",
                node=node,
                provider=provider,
                attempt=attempt,
            )

    def node_failed(
        self,
        *,
        node: str,
        provider: str | None,
        attempt: int,
        exc: Exception,
    ) -> None:
        with self._lock:
            self.current_stage = node
            self.current_provider = provider

            self.failure = {
                "node": node,
                "provider": provider,
                "attempt": attempt,
                "exception_type": type(exc).__name__,
                "message": str(exc),
                "timestamp": time.time(),
            }

            self._record_event(
                event="node_failed",
                node=node,
                provider=provider,
                attempt=attempt,
                exception_type=type(exc).__name__,
                message=str(exc),
            )

    def record_rate_limit(
        self,
        *,
        node: str,
        provider: str,
        attempt: int,
        info: RateLimitInfo,
    ) -> None:
        with self._lock:
            self.current_stage = node
            self.current_provider = provider

            self._record_event(
                event="rate_limit",
                node=node,
                provider=provider,
                attempt=attempt,
                status_code=info.status_code,
                retry_after_seconds=info.retry_after_seconds,
                reset_tokens_seconds=info.reset_tokens_seconds,
                remaining_tokens=info.remaining_tokens,
                limit_tokens=info.limit_tokens,
            )

    def record_markdown_gate(
        self,
        *,
        deterministic_repair_applied: bool,
        llm_repair_applied: bool,
    ) -> None:
        with self._lock:
            if deterministic_repair_applied:
                self.markdown_deterministic_repairs += 1

            if llm_repair_applied:
                self.markdown_llm_repairs += 1

            self._record_event(
                event="markdown_gate",
                deterministic_repair_applied=(deterministic_repair_applied),
                llm_repair_applied=(llm_repair_applied),
            )

    def record_editorial_review(self) -> None:
        with self._lock:
            self.editorial_reviews += 1

            self._record_event(
                event="editorial_review",
            )

    def record_revision(self) -> None:
        with self._lock:
            self.editorial_revisions += 1

            self._record_event(
                event="editorial_revision",
            )

    def record_image_attempt(
        self,
        image_id: str,
    ) -> None:
        with self._lock:
            self.image_attempts += 1
            self.image_ids.append(image_id)

            self._record_event(
                event="image_attempt",
                image_id=image_id,
            )

    def record_final_validation(
        self,
        errors: list[str],
    ) -> None:
        with self._lock:
            self.final_validation_failures += len(errors)

            self._record_event(
                event="final_validation",
                errors=list(errors),
            )

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> RunDiagnostics:
        diagnostics = cls(
            run_id=data["run_id"],
            topic=data.get("topic", ""),
        )

        diagnostics.started_at = data.get(
            "started_at",
            diagnostics.started_at,
        )

        diagnostics.status = data.get(
            "status",
            "running",
        )

        diagnostics.current_stage = data.get(
            "current_stage",
            "",
        )

        diagnostics.current_provider = data.get(
            "current_provider",
        )

        diagnostics.retry_count = data.get(
            "retry_count",
            0,
        )

        diagnostics.provider_attempts.update(
            data.get(
                "provider_attempts",
                {},
            )
        )

        markdown = data.get(
            "markdown",
            {},
        )

        diagnostics.markdown_deterministic_repairs = markdown.get(
            "deterministic_repairs",
            0,
        )

        diagnostics.markdown_llm_repairs = markdown.get(
            "llm_repairs",
            0,
        )

        diagnostics.editorial_reviews = data.get(
            "editorial_reviews",
            0,
        )

        diagnostics.editorial_revisions = data.get(
            "editorial_revisions",
            0,
        )

        diagnostics.image_attempts = data.get(
            "image_attempts",
            0,
        )

        diagnostics.image_ids = list(
            data.get(
                "image_ids",
                [],
            )
        )

        diagnostics.final_validation_failures = data.get(
            "final_validation_failures",
            0,
        )

        diagnostics.failure = data.get(
            "failure",
        )

        diagnostics.events = list(
            data.get(
                "events",
                [],
            )
        )

        return diagnostics

    def record_resume(self) -> None:
        with self._lock:
            previous_failure = self.failure

            self.status = "running"
            self.failure = None

            self._record_event(
                event="run_resumed",
                previous_failure=previous_failure,
            )

    def finish_success(
        self,
        result: dict,
    ) -> None:
        with self._lock:
            self.status = "success"

            self._record_event(
                event="run_finished",
                status="success",
            )

    def finish_failure(
        self,
        exc: Exception,
    ) -> None:
        with self._lock:
            self.status = "failed"

            if self.failure is None:
                self.failure = {
                    "node": self.current_stage or None,
                    "provider": (self.current_provider),
                    "attempt": None,
                    "exception_type": (type(exc).__name__),
                    "message": str(exc),
                    "timestamp": time.time(),
                }

            self._record_event(
                event="run_finished",
                status="failed",
            )


def diagnostics_path(
    run_id: str,
) -> Path:
    return Path("runs") / run_id / "diagnostics.json"


def load_diagnostics(
    run_id: str,
) -> dict:
    path = diagnostics_path(run_id)

    if not path.is_file():
        return {}

    return json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )


def format_cli_summary(
    data: dict,
) -> str:
    run_id = data.get(
        "run_id",
        "unknown",
    )

    stage = data.get("current_stage") or "unknown"

    provider = data.get("current_provider") or "none"

    retry_count = data.get(
        "retry_count",
        0,
    )

    provider_attempts = data.get(
        "provider_attempts",
        {},
    )

    attempts = 1

    if provider in provider_attempts:
        attempts = provider_attempts[provider]

    failure = data.get("failure") or {}

    exception_type = failure.get("exception_type") or "unknown"

    message = failure.get("message") or "unknown"

    return "\n".join(
        [
            f"Run ID: {run_id}",
            f"Stage: {stage}",
            f"Provider: {provider}",
            f"Attempts: {attempts}",
            f"Retries: {retry_count}",
            f"Failure: {exception_type}",
            f"Message: {message}",
            (f"Diagnostics: {diagnostics_path(run_id)}"),
        ]
    )


def instrument_node(
    node_name: str,
    node_function: Callable,
    *,
    provider: str | None = None,
):
    def wrapped(
        value,
        runtime,
    ):
        execution_info = runtime.execution_info

        attempt = execution_info.node_attempt if execution_info is not None else 1

        diagnostics = runtime.context["diagnostics"]

        diagnostics.node_started(
            node=node_name,
            provider=provider,
            attempt=attempt,
        )

        try:
            result = node_function(value)

        except Exception as exc:
            diagnostics.node_failed(
                node=node_name,
                provider=provider,
                attempt=attempt,
                exc=exc,
            )

            if provider == "groq":
                rate_limit_info = extract_rate_limit_info(
                    exc,
                )

                if rate_limit_info is not None:
                    diagnostics.record_rate_limit(
                        node=node_name,
                        provider=provider,
                        attempt=attempt,
                        info=rate_limit_info,
                    )

                    delay = get_provider_retry_delay_seconds(
                        rate_limit_info,
                    )

                    if delay is not None:
                        if delay > RATE_LIMIT_SHORT_WAIT_SECONDS:
                            raise RateLimitRetryExhausted(
                                rate_limit_info,
                            ) from exc

                        if attempt >= PROVIDER_RETRY_MAX_ATTEMPTS:
                            raise RateLimitRetryExhausted(
                                rate_limit_info,
                            ) from exc

                        time.sleep(delay)

            raise

        diagnostics.node_succeeded(
            node=node_name,
            provider=provider,
            attempt=attempt,
        )

        return result

    return wrapped


def get_current_diagnostics():
    try:
        runtime = get_runtime()
    except RuntimeError:
        return None

    context = runtime.context

    if not context:
        return None

    return context.get("diagnostics")
