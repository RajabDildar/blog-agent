"""PostgreSQL implementation of the ArticleRepository protocol."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from apps.api.db.models import Run
from apps.api.services.diagnostics_sink import WorkerSessionLocal

logger = logging.getLogger("blog_agent.article_repository")


class PostgresArticleRepository:
    """Persists and retrieves article content and asset manifests in PostgreSQL."""

    def __init__(self, session_factory: sessionmaker | None = None):
        self.session_factory = session_factory or WorkerSessionLocal

    def save_article(
        self,
        *,
        run_id: str,
        title: str,
        markdown: str,
        excerpt: str,
        assets: list[dict[str, Any]],
    ) -> None:
        """
        Durably stores final article content and asset manifest on the run row.
        Raises RuntimeError if the run record does not exist.
        """
        with self.session_factory() as session:
            run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if not run:
                raise RuntimeError(
                    f"Run {run_id} not found in database; cannot persist article."
                )

            run.article_title = title
            run.article_markdown = markdown
            run.article_excerpt = excerpt
            run.article_assets = assets
            session.commit()
            logger.info(f"Article for run {run_id} saved to PostgreSQL successfully.")

    def get_article(self, run_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            run = session.scalar(select(Run).where(Run.id == run_id))
            if not run or not run.article_markdown:
                return None
            return {
                "id": run.id,
                "title": run.article_title,
                "markdown": run.article_markdown,
                "excerpt": run.article_excerpt,
                "assets": run.article_assets,
            }
