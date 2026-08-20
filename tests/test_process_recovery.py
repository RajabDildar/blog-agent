import subprocess
import sys
from pathlib import Path

SCRIPT = r"""
import os
import sys
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from services.checkpointer import create_checkpointer


class RecoveryState(TypedDict):
    first: str
    second: str


database_path = Path(sys.argv[1])
first_marker = Path(sys.argv[2])
second_marker = Path(sys.argv[3])
mode = sys.argv[4]

handle = create_checkpointer(
    database_path,
)

try:
    def first_node(
        state: RecoveryState,
    ):
        first_marker.write_text(
            "completed",
            encoding="utf-8",
        )

        return {
            "first": "complete",
        }

    def second_node(
        state: RecoveryState,
    ):
        if mode == "crash":
            second_marker.write_text(
                "started",
                encoding="utf-8",
            )

            os._exit(23)

        second_marker.write_text(
            "completed",
            encoding="utf-8",
        )

        return {
            "second": "complete",
        }

    builder = StateGraph(
        RecoveryState,
    )

    builder.add_node(
        "first",
        first_node,
    )

    builder.add_node(
        "second",
        second_node,
    )

    builder.add_edge(
        START,
        "first",
    )

    builder.add_edge(
        "first",
        "second",
    )

    builder.add_edge(
        "second",
        END,
    )

    app = builder.compile(
        checkpointer=handle.saver,
    )

    config = {
        "configurable": {
            "thread_id": "process-recovery",
        },
    }

    if mode == "crash":
        app.invoke(
            {
                "first": "",
                "second": "",
            },
            config,
            durability="sync",
        )

    elif mode == "resume":
        result = app.invoke(
            None,
            config,
            durability="sync",
        )

        assert result == {
            "first": "complete",
            "second": "complete",
        }

    else:
        raise ValueError(
            f"Unknown mode: {mode}",
        )

finally:
    handle.close()
"""


def run_child(
    *,
    database_path: Path,
    first_marker: Path,
    second_marker: Path,
    mode: str,
):
    return subprocess.run(
        [
            sys.executable,
            "-c",
            SCRIPT,
            str(database_path),
            str(first_marker),
            str(second_marker),
            mode,
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )


def test_resume_after_process_termination(
    tmp_path,
):
    database_path = tmp_path / "checkpoints.sqlite"

    first_marker = tmp_path / "first.txt"

    second_marker = tmp_path / "second.txt"

    crashed = run_child(
        database_path=database_path,
        first_marker=first_marker,
        second_marker=second_marker,
        mode="crash",
    )

    assert crashed.returncode == 23
    assert database_path.exists()

    assert (
        first_marker.read_text(
            encoding="utf-8",
        )
        == "completed"
    )

    assert (
        second_marker.read_text(
            encoding="utf-8",
        )
        == "started"
    )

    resumed = run_child(
        database_path=database_path,
        first_marker=first_marker,
        second_marker=second_marker,
        mode="resume",
    )

    assert resumed.returncode == 0, resumed.stdout + "\n" + resumed.stderr

    assert (
        first_marker.read_text(
            encoding="utf-8",
        )
        == "completed"
    )

    assert (
        second_marker.read_text(
            encoding="utf-8",
        )
        == "completed"
    )
