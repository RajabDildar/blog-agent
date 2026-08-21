import json
import operator
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, TypedDict

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from graph import main_graph
from services.rate_limits import (
    RateLimitInfo,
    RateLimitRetryExhausted,
)
from services.run_diagnostics import (
    RunDiagnostics,
)


def _rate_limit_info(
    *,
    retry_after_seconds: float | None = 30.0,
) -> RateLimitInfo:
    return RateLimitInfo(
        provider="groq",
        status_code=429,
        retry_after_seconds=retry_after_seconds,
        reset_tokens_seconds=45.0,
        remaining_tokens=0,
        limit_tokens=8000,
    )


def test_run_marks_rate_limit_pause_and_exposes_resume_metadata(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    run_id = "r" * 32
    started = time.time()

    info = _rate_limit_info(
        retry_after_seconds=60.0,
    )

    def failing_invoke(*args, **kwargs):
        original_error = RuntimeError("groq 429")

        try:
            raise original_error
        except RuntimeError as cause:
            raise RateLimitRetryExhausted(info) from cause

    monkeypatch.setattr(
        main_graph,
        "_thread_exists",
        lambda candidate_run_id: False,
    )
    monkeypatch.setattr(
        main_graph.app,
        "invoke",
        failing_invoke,
    )

    with pytest.raises(RateLimitRetryExhausted) as raised:
        main_graph.run(
            "rate limit test",
            run_id=run_id,
        )

    exc = raised.value

    assert exc.run_id == run_id
    assert exc.resume_after is not None
    assert exc.resume_after >= started + 60.0

    data = json.loads(
        Path(
            "runs",
            run_id,
            "diagnostics.json",
        ).read_text(
            encoding="utf-8",
        )
    )

    assert data["status"] == "paused_rate_limit"
    assert data["resume_after"] == exc.resume_after
    assert data["failure"]["exception_type"] == "RuntimeError"
    assert any(event["event"] == "run_paused" for event in data["events"])


def test_resume_rejects_before_resume_after(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    run_id = "s" * 32
    diagnostics = RunDiagnostics(
        run_id=run_id,
        topic="resume timing",
    )

    info = _rate_limit_info()

    pause_error = RateLimitRetryExhausted(info)

    diagnostics.pause_rate_limit(
        info=info,
        resume_after=time.time() + 60.0,
        exc=pause_error,
    )

    monkeypatch.setattr(
        main_graph._checkpointer_handle.saver,
        "get_tuple",
        lambda config: object(),
    )

    monkeypatch.setattr(
        main_graph.app,
        "get_state",
        lambda config: SimpleNamespace(
            next=("worker",),
            values={"topic": "resume timing"},
        ),
    )

    def unexpected_invoke(*args, **kwargs):
        raise AssertionError("Graph must not be invoked before resume_after.")

    monkeypatch.setattr(
        main_graph.app,
        "invoke",
        unexpected_invoke,
    )

    with pytest.raises(
        ValueError,
        match="paused by provider rate limiting",
    ):
        main_graph.resume(run_id)


def test_resume_after_pause_uses_same_run_id_and_preserves_start_time(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    run_id = "t" * 32

    diagnostics = RunDiagnostics(
        run_id=run_id,
        topic="resume success",
    )

    original_started_at = diagnostics.started_at

    info = _rate_limit_info(
        retry_after_seconds=1.0,
    )

    diagnostics.pause_rate_limit(
        info=info,
        resume_after=time.time() - 1.0,
        exc=RateLimitRetryExhausted(info),
    )

    captured = {}

    monkeypatch.setattr(
        main_graph._checkpointer_handle.saver,
        "get_tuple",
        lambda config: object(),
    )

    monkeypatch.setattr(
        main_graph.app,
        "get_state",
        lambda config: SimpleNamespace(
            next=("worker",),
            values={"topic": "resume success"},
        ),
    )

    def successful_invoke(
        input_value,
        config,
        *,
        context,
        durability,
    ):
        captured["input"] = input_value
        captured["config"] = config
        captured["durability"] = durability

        return {
            "topic": "resume success",
        }

    monkeypatch.setattr(
        main_graph.app,
        "invoke",
        successful_invoke,
    )

    result = main_graph.resume(run_id)

    assert result["topic"] == "resume success"

    assert captured["input"] is None
    assert captured["config"]["configurable"]["thread_id"] == run_id
    assert captured["durability"] == "sync"

    restored = RunDiagnostics.from_dict(
        json.loads(
            Path(
                "runs",
                run_id,
                "diagnostics.json",
            ).read_text(
                encoding="utf-8",
            )
        )
    )

    assert restored.status == "success"
    assert restored.resume_after is None
    assert restored.started_at == original_started_at
    assert any(event["event"] == "run_resumed" for event in restored.events)


def test_langgraph_resume_preserves_successful_pending_sibling_work(
    tmp_path,
):
    class RecoveryState(TypedDict):
        events: Annotated[list[str], operator.add]

    attempts = {
        "successful": 0,
        "limited": 0,
    }

    info = _rate_limit_info()

    def fanout(state: RecoveryState):
        return [
            Send("successful", {}),
            Send("limited", {}),
        ]

    def successful(state: RecoveryState):
        attempts["successful"] += 1
        return {
            "events": ["successful"],
        }

    def limited(state: RecoveryState):
        attempts["limited"] += 1

        if attempts["limited"] == 1:
            raise RateLimitRetryExhausted(info)

        return {
            "events": ["limited"],
        }

    builder = StateGraph(RecoveryState)

    builder.add_node(
        "fanout",
        lambda state: {},
    )
    builder.add_node(
        "successful",
        successful,
    )
    builder.add_node(
        "limited",
        limited,
    )

    builder.add_edge(
        START,
        "fanout",
    )

    builder.add_conditional_edges(
        "fanout",
        fanout,
    )

    builder.add_edge(
        "successful",
        END,
    )
    builder.add_edge(
        "limited",
        END,
    )

    connection = sqlite3.connect(
        tmp_path / "recovery.sqlite",
        check_same_thread=False,
    )

    checkpointer = SqliteSaver(connection)
    checkpointer.setup()

    graph = builder.compile(
        checkpointer=checkpointer,
    )

    config = {
        "configurable": {
            "thread_id": "pending-write-test",
        },
    }

    with pytest.raises(RateLimitRetryExhausted):
        graph.invoke(
            {
                "events": [],
            },
            config,
            durability="sync",
        )

    assert attempts["successful"] == 1
    assert attempts["limited"] == 1

    result = graph.invoke(
        None,
        config,
        durability="sync",
    )

    assert attempts["successful"] == 1
    assert attempts["limited"] == 2
    assert sorted(result["events"]) == [
        "limited",
        "successful",
    ]

    connection.close()
