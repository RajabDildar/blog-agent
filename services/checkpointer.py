from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from schemas.models import (
    EditorialIssue,
    EditorialReview,
    Plan,
    ResearchEvidence,
    SectionOutput,
    Task,
)

PathLike = str | Path


@dataclass
class CheckpointerHandle:
    """
    Own the SQLite connection and its LangGraph checkpointer.

    The handle keeps the connection alive for as long as the compiled
    graph needs the checkpointer and provides an explicit lifecycle boundary.
    """

    path: Path
    connection: sqlite3.Connection
    saver: SqliteSaver

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()


def create_checkpointer(
    path: PathLike,
) -> CheckpointerHandle:
    """
    Create and initialize a synchronous SQLite LangGraph checkpointer.

    The caller owns the returned handle and must keep it alive for as long
    as the compiled graph uses the checkpointer.
    """
    checkpoint_path = Path(path)

    checkpoint_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        checkpoint_path,
        check_same_thread=False,
    )

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ResearchEvidence,
            Plan,
            Task,
            SectionOutput,
            EditorialReview,
            EditorialIssue,
        ],
    )

    saver = SqliteSaver(
        connection,
        serde=serde,
    )

    try:
        saver.setup()
    except Exception:
        connection.close()
        raise

    return CheckpointerHandle(
        path=checkpoint_path,
        connection=connection,
        saver=saver,
    )
