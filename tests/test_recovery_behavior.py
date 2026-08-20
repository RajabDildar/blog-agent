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

                raise RuntimeError(
                    "parallel worker failed",
                )

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


def test_resume_retries_failed_editor_without_rerunning_merge(
    tmp_path,
):
    handle = create_checkpointer(
        tmp_path / "checkpoints.sqlite",
    )

    try:
        calls = {
            "merge": 0,
            "editor": 0,
            "article_validator": 0,
        }

        def merge(
            state: RecoveryState,
        ):
            calls["merge"] += 1

            return {
                "results": {
                    "merge": "complete",
                },
            }

        def editor(
            state: RecoveryState,
        ):
            calls["editor"] += 1

            if calls["editor"] == 1:
                raise RuntimeError("editor failed")

            return {
                "results": {
                    "editor": "complete",
                },
            }

        def article_validator(
            state: RecoveryState,
        ):
            calls["article_validator"] += 1

            return {
                "results": {
                    "article_validator": "complete",
                },
            }

        builder = StateGraph(
            RecoveryState,
        )

        builder.add_node(
            "merge",
            merge,
        )

        builder.add_node(
            "editor",
            editor,
        )

        builder.add_node(
            "article_validator",
            article_validator,
        )

        builder.add_edge(
            START,
            "merge",
        )

        builder.add_edge(
            "merge",
            "editor",
        )

        builder.add_edge(
            "editor",
            "article_validator",
        )

        builder.add_edge(
            "article_validator",
            END,
        )

        app = builder.compile(
            checkpointer=handle.saver,
        )

        config = {
            "configurable": {
                "thread_id": "editor-recovery",
            },
        }

        with pytest.raises(
            RuntimeError,
            match="editor failed",
        ):
            app.invoke(
                {
                    "results": {},
                },
                config,
                durability="sync",
            )

        assert calls == {
            "merge": 1,
            "editor": 1,
            "article_validator": 0,
        }

        failed_state = app.get_state(
            config,
        )

        assert failed_state.values["results"] == {
            "merge": "complete",
        }

        assert failed_state.next == ("editor",)

        result = app.invoke(
            None,
            config,
            durability="sync",
        )

        assert result["results"] == {
            "merge": "complete",
            "editor": "complete",
            "article_validator": "complete",
        }

        assert calls == {
            "merge": 1,
            "editor": 2,
            "article_validator": 1,
        }

    finally:
        handle.close()


def test_resume_retries_failed_article_repair_without_rerunning_validator(
    tmp_path,
):
    handle = create_checkpointer(
        tmp_path / "checkpoints.sqlite",
    )

    try:
        calls = {
            "article_validator": 0,
            "repair": 0,
            "image_planner": 0,
        }

        def article_validator(
            state: RecoveryState,
        ):
            calls["article_validator"] += 1

            return {
                "results": {
                    "article_validator": "needs_repair",
                },
            }

        def repair(
            state: RecoveryState,
        ):
            calls["repair"] += 1

            if calls["repair"] == 1:
                raise RuntimeError("article repair failed")

            return {
                "results": {
                    "repair": "complete",
                },
            }

        def image_planner(
            state: RecoveryState,
        ):
            calls["image_planner"] += 1

            return {
                "results": {
                    "image_planner": "complete",
                },
            }

        builder = StateGraph(
            RecoveryState,
        )

        builder.add_node(
            "article_validator",
            article_validator,
        )

        builder.add_node(
            "repair",
            repair,
        )

        builder.add_node(
            "image_planner",
            image_planner,
        )

        builder.add_edge(
            START,
            "article_validator",
        )

        builder.add_edge(
            "article_validator",
            "repair",
        )

        builder.add_edge(
            "repair",
            "image_planner",
        )

        builder.add_edge(
            "image_planner",
            END,
        )

        app = builder.compile(
            checkpointer=handle.saver,
        )

        config = {
            "configurable": {
                "thread_id": "article-repair-recovery",
            },
        }

        with pytest.raises(
            RuntimeError,
            match="article repair failed",
        ):
            app.invoke(
                {
                    "results": {},
                },
                config,
                durability="sync",
            )

        assert calls == {
            "article_validator": 1,
            "repair": 1,
            "image_planner": 0,
        }

        failed_state = app.get_state(
            config,
        )

        assert failed_state.values["results"] == {
            "article_validator": "needs_repair",
        }

        assert failed_state.next == ("repair",)

        result = app.invoke(
            None,
            config,
            durability="sync",
        )

        assert result["results"] == {
            "article_validator": "needs_repair",
            "repair": "complete",
            "image_planner": "complete",
        }

        assert calls == {
            "article_validator": 1,
            "repair": 2,
            "image_planner": 1,
        }

    finally:
        handle.close()


def test_resume_retries_failed_image_generation_without_rerunning_planner(
    tmp_path,
):
    handle = create_checkpointer(
        tmp_path / "checkpoints.sqlite",
    )

    try:
        calls = {
            "image_planner": 0,
            "image_generator": 0,
            "validator": 0,
        }

        def image_planner(
            state: RecoveryState,
        ):
            calls["image_planner"] += 1

            return {
                "results": {
                    "image_planner": "complete",
                },
            }

        def image_generator(
            state: RecoveryState,
        ):
            calls["image_generator"] += 1

            if calls["image_generator"] == 1:
                raise RuntimeError(
                    "image generation failed",
                )

            return {
                "results": {
                    "image_generator": "complete",
                },
            }

        def validator(
            state: RecoveryState,
        ):
            calls["validator"] += 1

            return {
                "results": {
                    "validator": "complete",
                },
            }

        builder = StateGraph(
            RecoveryState,
        )

        builder.add_node(
            "image_planner",
            image_planner,
        )

        builder.add_node(
            "image_generator",
            image_generator,
        )

        builder.add_node(
            "validator",
            validator,
        )

        builder.add_edge(
            START,
            "image_planner",
        )

        builder.add_edge(
            "image_planner",
            "image_generator",
        )

        builder.add_edge(
            "image_generator",
            "validator",
        )

        builder.add_edge(
            "validator",
            END,
        )

        app = builder.compile(
            checkpointer=handle.saver,
        )

        config = {
            "configurable": {
                "thread_id": "image-generation-recovery",
            },
        }

        with pytest.raises(
            RuntimeError,
            match="image generation failed",
        ):
            app.invoke(
                {
                    "results": {},
                },
                config,
                durability="sync",
            )

        assert calls == {
            "image_planner": 1,
            "image_generator": 1,
            "validator": 0,
        }

        failed_state = app.get_state(
            config,
        )

        assert failed_state.values["results"] == {
            "image_planner": "complete",
        }

        assert failed_state.next == ("image_generator",)

        result = app.invoke(
            None,
            config,
            durability="sync",
        )

        assert result["results"] == {
            "image_planner": "complete",
            "image_generator": "complete",
            "validator": "complete",
        }

        assert calls == {
            "image_planner": 1,
            "image_generator": 2,
            "validator": 1,
        }

    finally:
        handle.close()
