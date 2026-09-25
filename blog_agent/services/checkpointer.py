from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from blog_agent.schemas.models import (
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
    Own the SQLite/Postgres connection and its LangGraph checkpointer.

    The handle keeps the connection alive for as long as the compiled
    graph needs the checkpointer and provides an explicit lifecycle boundary.
    """

    path: Path | None
    connection: Any
    saver: Any

    def close(self) -> None:
        """Close the underlying connection or pool."""
        if self.connection is not None:
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


def _get_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            ResearchEvidence,
            Plan,
            Task,
            SectionOutput,
            EditorialReview,
            EditorialIssue,
        ],
    )


def create_checkpointer(
    path: PathLike | None = None,
    *,
    backend: str | None = None,
    database_url: str | None = None,
) -> CheckpointerHandle:
    """
    Create and initialize a synchronous LangGraph checkpointer (SQLite or PostgreSQL).

    The caller owns the returned handle and must keep it alive for as long
    as the compiled graph uses the checkpointer.
    """
    if backend is None:
        if path is not None:
            backend = "sqlite"
        else:
            from blog_agent.config.settings import CHECKPOINT_BACKEND
            backend = CHECKPOINT_BACKEND

    serde = _get_serde()

    if backend == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool
        from psycopg.rows import dict_row

        if database_url is None:
            from blog_agent.config.settings import DATABASE_URL
            database_url = DATABASE_URL

        clean_url = database_url.replace("postgresql+psycopg://", "postgresql://")
        pool = ConnectionPool(
            conninfo=clean_url,
            max_size=20,
            open=True,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        saver = PostgresSaver(pool, serde=serde)
        try:
            saver.setup()
        except Exception:
            pool.close()
            raise

        return CheckpointerHandle(
            path=None,
            connection=pool,
            saver=saver,
        )

    # SQLite fallback / default
    if path is None:
        from blog_agent.config.settings import CHECKPOINT_SQLITE_PATH
        path = CHECKPOINT_SQLITE_PATH

    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        checkpoint_path,
        check_same_thread=False,
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
