import threading

import pytest
from langgraph.graph import END, START, StateGraph
from typing_extensions import Annotated, TypedDict

from services.checkpointer import create_checkpointer


def merge_results(
    current: dict[str, str],
    update: dict[str, str],
) -> dict[str, str]:
    return {
        **current,
        **update,
    }


class RecoveryState(TypedDict):
    results: Annotated[
        dict[str, str],
        merge_results,
    ]


def test_resume_retries_failed_worker_without_rerunning_completed_worker(
    tmp_path,
):
    handle = create_checkpointer(
        tmp_path / "checkpoints.sqlite",
    )

    try:
        calls = {
            "worker_one": 0,
            "worker_two": 0,
        }

        def worker_one(
            state: RecoveryState,
        ):
            calls["worker_one"] += 1

            return {
                "results": {
                    "worker_one": "complete",
                },
            }

        def worker_two(
            state: RecoveryState,
        ):
            calls["worker_two"] += 1

            if calls["worker_two"] == 1:
                raise RuntimeError("worker two failed")

            return {
                "results": {
                    "worker_two": "complete",
                },
            }

        builder = StateGraph(
            RecoveryState,
        )

        builder.add_node(
            "worker_one",
            worker_one,
        )

        builder.add_node(
            "worker_two",
            worker_two,
        )

        builder.add_edge(
            START,
            "worker_one",
        )

        builder.add_edge(
            "worker_one",
            "worker_two",
        )

        builder.add_edge(
            "worker_two",
            END,
        )

        app = builder.compile(
            checkpointer=handle.saver,
        )

        config = {
            "configurable": {
                "thread_id": "sequential-worker-recovery",
            },
        }

        with pytest.raises(
            RuntimeError,
            match="worker two failed",
        ):
            app.invoke(
                {
                    "results": {},
                },
                config,
                durability="sync",
            )

        assert calls == {
            "worker_one": 1,
            "worker_two": 1,
        }

        failed_state = app.get_state(
            config,
        )

        assert failed_state.values["results"] == {
            "worker_one": "complete",
        }

        assert failed_state.next == ("worker_two",)

        result = app.invoke(
            None,
            config,
            durability="sync",
        )

        assert result["results"] == {
            "worker_one": "complete",
            "worker_two": "complete",
        }

        assert calls == {
            "worker_one": 1,
            "worker_two": 2,
        }

        completed_state = app.get_state(
            config,
        )

        assert completed_state.next == ()

    finally:
        handle.close()


def test_resume_preserves_successful_parallel_sibling(
    tmp_path,
):
    handle = create_checkpointer(
        tmp_path / "checkpoints.sqlite",
    )

    try:
        calls = {
            "successful_worker": 0,
            "failing_worker": 0,
        }

        successful_worker_completed = threading.Event()

        def successful_worker(
            state: RecoveryState,
        ):

            calls["successful_worker"] += 1

            successful_worker_completed.set()

            return {
                "results": {
                    "successful_worker": "complete",
                },
            }

        def failing_worker(
            state: RecoveryState,
        ):
            calls["failing_worker"] += 1

            if calls["failing_worker"] == 1:
                completed = successful_worker_completed.wait(
                    timeout=2,
                )

                assert completed

                raise RuntimeError("parallel worker failed")

            return {
                "results": {
                    "failing_worker": "complete",
                },
            }

        builder = StateGraph(
            RecoveryState,
        )

        builder.add_node(
            "successful_worker",
            successful_worker,
        )

        builder.add_node(
            "failing_worker",
            failing_worker,
        )

        builder.add_edge(
            START,
            "successful_worker",
        )

        builder.add_edge(
            START,
            "failing_worker",
        )

        builder.add_edge(
            "successful_worker",
            END,
        )

        builder.add_edge(
            "failing_worker",
            END,
        )

        app = builder.compile(
            checkpointer=handle.saver,
        )

        config = {
            "configurable": {
                "thread_id": "parallel-worker-recovery",
            },
        }

        with pytest.raises(
            RuntimeError,
            match="parallel worker failed",
        ):
            app.invoke(
                {
                    "results": {},
                },
                config,
                durability="sync",
            )

        assert calls == {
            "successful_worker": 1,
            "failing_worker": 1,
        }

        result = app.invoke(
            None,
            config,
            durability="sync",
        )

        assert result["results"] == {
            "successful_worker": "complete",
            "failing_worker": "complete",
        }

        assert calls == {
            "successful_worker": 1,
            "failing_worker": 2,
        }

        completed_state = app.get_state(
            config,
        )

        assert completed_state.next == ()

    finally:
        handle.close()
