import sqlite3

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from graph.main_graph import build_graph
from services.checkpointer import (
    CheckpointerHandle,
    create_checkpointer,
)


def test_create_checkpointer_creates_sqlite_database(
    tmp_path,
):
    checkpoint_path = tmp_path / "nested" / "checkpoints.sqlite"

    handle = create_checkpointer(
        checkpoint_path,
    )

    try:
        assert isinstance(
            handle,
            CheckpointerHandle,
        )
        assert handle.path == checkpoint_path
        assert checkpoint_path.is_file()
        assert isinstance(
            handle.connection,
            sqlite3.Connection,
        )
    finally:
        handle.close()


def test_create_checkpointer_initializes_checkpoint_schema(
    tmp_path,
):
    checkpoint_path = tmp_path / "checkpoints.sqlite"

    handle = create_checkpointer(
        checkpoint_path,
    )

    try:
        tables = {
            row[0]
            for row in handle.connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        assert "checkpoints" in tables
        assert "writes" in tables
    finally:
        handle.close()


def test_create_checkpointer_can_be_used_as_context_manager(
    tmp_path,
):
    checkpoint_path = tmp_path / "checkpoints.sqlite"

    with create_checkpointer(checkpoint_path) as handle:
        assert not handle.connection.execute("SELECT 1").fetchone() is None

    with pytest.raises(
        sqlite3.ProgrammingError,
    ):
        handle.connection.execute("SELECT 1")


def test_build_graph_uses_supplied_checkpointer(
    tmp_path,
):
    checkpoint_path = tmp_path / "graph-checkpoints.sqlite"

    handle = create_checkpointer(
        checkpoint_path,
    )

    try:
        graph = build_graph(
            handle.saver,
        )

        assert isinstance(
            graph.checkpointer,
            SqliteSaver,
        )
        assert graph.checkpointer is handle.saver
    finally:
        handle.close()
