import pytest
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from graph import main_graph
from services.checkpointer import create_checkpointer
from services.run_diagnostics import (
    RunDiagnostics,
    load_diagnostics,
)


class ResumeState(TypedDict):
    value: int
    topic: str


def build_failing_graph(
    saver,
):
    calls = {
        "increment": 0,
        "failing": 0,
        "finish": 0,
    }

    def increment(
        state: ResumeState,
    ):
        calls["increment"] += 1

        return {
            "value": state["value"] + 1,
        }

    def failing(
        state: ResumeState,
    ):
        calls["failing"] += 1

        if calls["failing"] == 1:
            raise RuntimeError("deterministic failure")

        return {
            "value": state["value"] + 1,
        }

    def finish(
        state: ResumeState,
    ):
        calls["finish"] += 1

        return {
            "value": state["value"] + 1,
        }

    builder = StateGraph(
        ResumeState,
    )

    builder.add_node(
        "increment",
        increment,
    )

    builder.add_node(
        "failing",
        failing,
    )

    builder.add_node(
        "finish",
        finish,
    )

    builder.add_edge(
        START,
        "increment",
    )

    builder.add_edge(
        "increment",
        "failing",
    )

    builder.add_edge(
        "failing",
        "finish",
    )

    builder.add_edge(
        "finish",
        END,
    )

    return (
        builder.compile(
            checkpointer=saver,
        ),
        calls,
    )


def test_resume_unknown_run_rejected():
    with pytest.raises(
        ValueError,
        match="Unknown run ID: unknown-resume-run",
    ):
        main_graph.resume(
            "unknown-resume-run",
        )


def test_resume_rejects_completed_run(
    tmp_path,
):
    handle = create_checkpointer(
        tmp_path / "checkpoints.sqlite",
    )

    try:
        app, calls = build_completed_graph(
            handle.saver,
        )

        run_id = "completed-run"

        config = {
            "configurable": {
                "thread_id": run_id,
            },
        }

        result = app.invoke(
            {
                "value": 0,
                "topic": "completed",
            },
            config,
            durability="sync",
        )

        assert result["value"] == 2
        assert calls["finish"] == 1

        original_app = main_graph.app
        original_handle = main_graph._checkpointer_handle

        main_graph.app = app
        main_graph._checkpointer_handle = handle

        try:
            with pytest.raises(
                ValueError,
                match=("Run completed-run has already completed successfully."),
            ):
                main_graph.resume(
                    run_id,
                )
        finally:
            main_graph.app = original_app
            main_graph._checkpointer_handle = original_handle

    finally:
        handle.close()


def test_resume_continues_from_checkpoint(
    tmp_path,
):
    handle = create_checkpointer(
        tmp_path / "checkpoints.sqlite",
    )

    try:
        app, calls = build_failing_graph(
            handle.saver,
        )

        run_id = "resume-run"

        config = {
            "configurable": {
                "thread_id": run_id,
            },
        }

        with pytest.raises(
            RuntimeError,
            match="deterministic failure",
        ):
            app.invoke(
                {
                    "value": 0,
                    "topic": "resume",
                },
                config,
                durability="sync",
            )

        assert calls["increment"] == 1
        assert calls["failing"] == 1
        assert calls["finish"] == 0

        state = app.get_state(
            config,
        )

        assert state.values["value"] == 1
        assert state.next == ("failing",)

        result = app.invoke(
            None,
            config,
            durability="sync",
        )

        assert result["value"] == 3
        assert calls["increment"] == 1
        assert calls["failing"] == 2
        assert calls["finish"] == 1

        final_state = app.get_state(
            config,
        )

        assert final_state.next == ()

    finally:
        handle.close()


def test_resume_preserves_diagnostics_history(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    handle = create_checkpointer(
        tmp_path / "checkpoints.sqlite",
    )

    try:
        app, _ = build_failing_graph(
            handle.saver,
        )

        run_id = "diagnostics-resume"

        config = {
            "configurable": {
                "thread_id": run_id,
            },
        }

        diagnostics = RunDiagnostics(
            run_id=run_id,
            topic="diagnostics",
        )

        try:
            app.invoke(
                {
                    "value": 0,
                    "topic": "diagnostics",
                },
                config,
                durability="sync",
                context={
                    "diagnostics": diagnostics,
                },
            )
        except RuntimeError as exc:
            diagnostics.finish_failure(
                exc,
            )

        original_started_at = diagnostics.started_at
        original_event_count = len(diagnostics.events)

        diagnostics_data = load_diagnostics(
            run_id,
        )

        assert diagnostics_data
        assert original_event_count > 0

        original_app = main_graph.app
        original_handle = main_graph._checkpointer_handle

        main_graph.app = app
        main_graph._checkpointer_handle = handle

        try:
            result = main_graph.resume(
                run_id,
            )

            assert result["value"] == 3

            resumed_data = load_diagnostics(
                run_id,
            )

            assert resumed_data["run_id"] == run_id
            assert resumed_data["started_at"] == original_started_at
            assert len(resumed_data["events"]) > original_event_count

            assert any(
                event["event"] == "run_resumed" for event in resumed_data["events"]
            )
            assert resumed_data["status"] == "success"
            assert resumed_data["failure"] is None
            assert resumed_data["retry_count"] == diagnostics.retry_count

        finally:
            main_graph.app = original_app
            main_graph._checkpointer_handle = original_handle

    finally:
        handle.close()


def build_completed_graph(
    saver,
):
    calls = {
        "finish": 0,
    }

    def increment(
        state: ResumeState,
    ):
        return {
            "value": state["value"] + 1,
        }

    def finish(
        state: ResumeState,
    ):
        calls["finish"] += 1

        return {
            "value": state["value"] + 1,
        }

    builder = StateGraph(
        ResumeState,
    )

    builder.add_node(
        "increment",
        increment,
    )

    builder.add_node(
        "finish",
        finish,
    )

    builder.add_edge(
        START,
        "increment",
    )

    builder.add_edge(
        "increment",
        "finish",
    )

    builder.add_edge(
        "finish",
        END,
    )

    return (
        builder.compile(
            checkpointer=saver,
        ),
        calls,
    )
