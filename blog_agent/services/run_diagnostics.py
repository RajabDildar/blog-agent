import json
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from langgraph.runtime import get_runtime

from blog_agent.config.settings import (
    PROVIDER_RETRY_MAX_ATTEMPTS,
    RATE_LIMIT_SHORT_WAIT_SECONDS,
)
from blog_agent.services.rate_limits import (
    RateLimitInfo,
    RateLimitRetryExhausted,
    extract_rate_limit_info,
    get_provider_retry_delay_seconds,
)


@runtime_checkable
class DiagnosticsSink(Protocol):
    """Abstraction for diagnostics and event persistence across CLI, files, and DB."""

    def record_event(self, run_id: str, event: dict[str, Any]) -> None:
        """Record a single runtime event."""
        ...

    def record_summary(self, run_id: str, summary: dict[str, Any]) -> None:
        """Persist or update the diagnostics summary snapshot."""
        ...


class FileDiagnosticsSink:
    """Default local file diagnostics sink for CLI and tests."""

    def __init__(self, run_id: str):
        self.run_id = run_id

    @property
    def path(self) -> Path:
        return Path("runs") / self.run_id / "diagnostics.json"

    def record_event(self, run_id: str, event: dict[str, Any]) -> None:
        # File sink writes snapshot when events occur
        pass

    def record_summary(self, run_id: str, summary: dict[str, Any]) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )


class RunDiagnostics:
    def __init__(
        self,
        *,
        run_id: str,
        topic: str = "",
        original_input: str | None = None,
        sink: DiagnosticsSink | None = None,
    ):
        self.run_id = run_id
        self.original_input = (
            original_input if original_input is not None else topic
        )
        self.topic = topic
        self.sink: DiagnosticsSink = (
            sink if sink is not None else FileDiagnosticsSink(run_id)
        )
        self.started_at = time.time()

        self.status = "running"
        self.intent_status = ""
        self.intent_category = ""
        self.intent_message = ""
        self.clarification_count = 0
        self.proposed_topic = ""

        self.resume_after: float | None = None

        self.current_stage = ""
        self.current_provider: str | None = None

        self.retry_count = 0

        self.provider_attempts: dict[str, int] = defaultdict(int)
        self.provider_calls: dict[str, int] = defaultdict(int)

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
            "original_input": self.original_input,
            "topic": self.topic,
            "status": self.status,
            "intent_status": self.intent_status,
            "intent_category": self.intent_category,
            "intent_message": self.intent_message,
            "clarification_count": self.clarification_count,
            "proposed_topic": self.proposed_topic,
            "resume_after": self.resume_after,
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
            "provider_calls": dict(self.provider_calls),
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
        self.sink.record_summary(self.run_id, self._snapshot())

    def _record_event(
        self,
        *,
        event: str,
        **payload: Any,
    ) -> None:
        event_dict = {
            "timestamp": time.time(),
            "event": event,
            **payload,
        }
        self.events.append(event_dict)
        self.sink.record_event(self.run_id, event_dict)
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

    def record_provider_call(self, provider: str) -> None:
        """Record one outbound provider invocation, separate from node attempts."""
        with self._lock:
            self.provider_calls[provider] += 1
            self._record_event(event="provider_call", provider=provider)

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

    def record_intent_check_started(self) -> None:
        with self._lock:
            self._record_event(event="intent_check_started")

    def record_intent_check_succeeded(
        self,
        *,
        provider: str,
        outcome: str,
    ) -> None:
        with self._lock:
            self._record_event(
                event="intent_check_succeeded",
                provider=provider,
                outcome=outcome,
            )

    def record_intent_provider_fallback(
        self,
        *,
        failed_provider: str,
        exc: Exception,
    ) -> None:
        with self._lock:
            self._record_event(
                event="intent_provider_fallback",
                failed_provider=failed_provider,
                exception_type=type(exc).__name__,
                message=str(exc),
            )

    def record_clarification_required(
        self,
        *,
        question: str,
        options: list[str],
    ) -> None:
        with self._lock:
            self.clarification_count += 1
            self.intent_status = "needs_clarification"
            self._record_event(
                event="clarification_required",
                question=question,
                options=list(options),
            )

    def record_topic_confirmation_required(
        self,
        *,
        proposed_topic: str,
    ) -> None:
        with self._lock:
            self.intent_status = "needs_confirmation"
            self.proposed_topic = proposed_topic
            self._record_event(
                event="topic_confirmation_required",
                proposed_topic=proposed_topic,
            )

    def record_topic_finalized(
        self,
        topic: str,
    ) -> None:
        with self._lock:
            self.topic = topic
            self.intent_status = "safe"
            self._record_event(
                event="topic_finalized",
                topic=topic,
            )

    def record_input_blocked(
        self,
        *,
        category: str,
        message: str,
    ) -> None:
        with self._lock:
            self.status = "blocked"
            self.intent_status = "blocked"
            self.intent_category = category
            self.intent_message = message
            self._record_event(
                event="input_blocked",
                category=category,
                message=message,
            )

    def record_input_invalid(
        self,
        *,
        reason: str,
        message: str,
    ) -> None:
        with self._lock:
            self.status = "invalid"
            self.intent_status = "invalid"
            self.intent_category = reason
            self.intent_message = message
            self._record_event(
                event="input_invalid",
                reason=reason,
                message=message,
            )

    def record_input_cancelled(self) -> None:
        with self._lock:
            self.status = "cancelled"
            self.intent_status = "cancelled"
            self._record_event(
                event="input_cancelled",
            )

    def record_intent_check_failed(
        self,
        exc: Exception,
    ) -> None:
        with self._lock:
            self._record_event(
                event="intent_check_failed",
                exception_type=type(exc).__name__,
                message=str(exc),
            )

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        sink: DiagnosticsSink | None = None,
    ) -> RunDiagnostics:
        diagnostics = cls(
            run_id=data["run_id"],
            topic=data.get("topic", ""),
            original_input=data.get("original_input"),
            sink=sink,
        )

        diagnostics.intent_status = data.get(
            "intent_status",
            "",
        )

        diagnostics.intent_category = data.get(
            "intent_category",
            "",
        )

        diagnostics.intent_message = data.get(
            "intent_message",
            "",
        )

        diagnostics.clarification_count = data.get(
            "clarification_count",
            0,
        )

        diagnostics.proposed_topic = data.get(
            "proposed_topic",
            "",
        )

        diagnostics.started_at = data.get(
            "started_at",
            diagnostics.started_at,
        )

        diagnostics.status = data.get(
            "status",
            "running",
        )

        diagnostics.resume_after = data.get(
            "resume_after",
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

        diagnostics.provider_calls.update(
            data.get(
                "provider_calls",
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

    def pause_rate_limit(
        self,
        *,
        info: RateLimitInfo,
        resume_after: float | None,
        exc: Exception,
    ) -> None:
        with self._lock:
            self.status = "paused_rate_limit"
            self.resume_after = resume_after

            if self.failure is None:
                cause = exc.__cause__ or exc
                self.failure = {
                    "node": self.current_stage or None,
                    "provider": self.current_provider or info.provider,
                    "attempt": None,
                    "exception_type": type(cause).__name__,
                    "message": str(cause),
                    "timestamp": time.time(),
                }

            self._record_event(
                event="run_paused",
                status="paused_rate_limit",
                resume_after=resume_after,
                provider=info.provider,
                status_code=info.status_code,
                retry_after_seconds=info.retry_after_seconds,
                reset_tokens_seconds=info.reset_tokens_seconds,
                remaining_tokens=info.remaining_tokens,
                limit_tokens=info.limit_tokens,
            )

    def record_resume(self) -> None:
        with self._lock:
            previous_failure = self.failure

            self.status = "running"
            self.resume_after = None
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
            self.resume_after = None

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
            self.resume_after = None

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

    status = data.get(
        "status",
        "unknown",
    )

    resume_after = data.get(
        "resume_after",
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

    lines = [
        f"Run ID: {run_id}",
        f"Status: {status}",
    ]

    if data.get("original_input"):
        lines.append(f"Original Input: {data['original_input']}")
    if data.get("topic"):
        lines.append(f"Topic: {data['topic']}")
    if data.get("intent_status"):
        lines.append(f"Intent Status: {data['intent_status']}")
    if data.get("intent_category"):
        lines.append(f"Intent Category: {data['intent_category']}")
    if data.get("clarification_count"):
        lines.append(f"Clarifications: {data['clarification_count']}")

    lines.extend(
        [
            f"Stage: {stage}",
            f"Provider: {provider}",
            f"Attempts: {attempts}",
            f"Retries: {retry_count}",
            f"Resume after: {resume_after}",
            f"Failure: {exception_type}",
            f"Message: {message}",
            (f"Diagnostics: {diagnostics_path(run_id)}"),
        ]
    )

    return "\n".join(lines)


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
