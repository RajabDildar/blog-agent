"""Integration test for completion transaction boundary, PostgreSQL persistence, and rollback handling."""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.config import get_settings
from apps.api.db.models import Run, RunStatus
from blog_agent.services.storage import publish_blog

settings = get_settings()
engine = create_engine(settings.TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

from sqlalchemy import text

RUN_ID = "c" * 32
FAIL_RUN_ID = "f" * 32


@pytest.fixture(autouse=True)
def setup_db():
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM run_events; DELETE FROM runs; DELETE FROM sessions; DELETE FROM users;"
            )
        )
    yield
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM run_events; DELETE FROM runs; DELETE FROM sessions; DELETE FROM users;"
            )
        )


def test_completion_transaction_persists_article(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestingSessionLocal() as db:
        run = Run(
            id=RUN_ID,
            original_input="Tx Input",
            topic="Tx Topic",
            status=RunStatus.RUNNING.value,
            visibility="private",
        )
        db.add(run)
        db.commit()

        md_content = """# Architecture of High-Performance Systems

High-performance software systems require low latency and predictable memory allocations.

## Key Design Considerations

Memory management and I/O efficiency dictate system throughput.
"""

        publish_blog(
            title="Architecture of High-Performance Systems",
            markdown=md_content,
            run_id=RUN_ID,
            image_results=[],
            db_session=db,
        )

        db.refresh(run)
        assert run.status == RunStatus.COMPLETED.value
        assert run.completed_at is not None
        assert run.article_title == "Architecture of High-Performance Systems"
        assert "High-performance software systems" in run.article_markdown
        assert (
            "High-performance software systems require low latency"
            in run.article_excerpt
        )


@patch("blog_agent.services.storage.upload_run_image")
def test_completion_transaction_rollback_on_upload_failure(
    mock_upload, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    mock_upload.side_effect = RuntimeError("Cloudinary upload connection error")

    with TestingSessionLocal() as db:
        run = Run(
            id=FAIL_RUN_ID,
            original_input="Fail Input",
            status=RunStatus.RUNNING.value,
        )
        db.add(run)
        db.commit()

        staged_dir = tmp_path / "runs" / FAIL_RUN_ID / "images"
        staged_dir.mkdir(parents=True, exist_ok=True)
        staged_file = staged_dir / "diagram.png"
        staged_file.write_bytes(b"data")

        pub_dir = tmp_path / "published" / f"Fail_{FAIL_RUN_ID}"
        pub_dir.mkdir(parents=True, exist_ok=True)
        pub_file = pub_dir / "diagram.png"
        md_img_path = pub_file

        monkeypatch.setattr(
            "blog_agent.services.storage.run_images_dir", lambda r: staged_dir
        )
        monkeypatch.setattr(
            "blog_agent.services.storage.published_images_dir",
            lambda title, run_id: pub_dir,
        )
        monkeypatch.setattr(
            "blog_agent.services.storage.is_cloudinary_configured", lambda: True
        )

        image_results = [
            {
                "id": "img1",
                "filename": "diagram.png",
                "staged_path": str(staged_file),
                "published_path": str(pub_file),
                "markdown_path": str(md_img_path),
                "status": "inserted",
            }
        ]

        with pytest.raises(RuntimeError, match="Cloudinary upload connection error"):
            publish_blog(
                title="Fail",
                markdown="# Fail\n\n![Img](diagram.png)",
                run_id=FAIL_RUN_ID,
                image_results=image_results,
                db_session=db,
            )

        db.refresh(run)
        # Status remains RUNNING, not COMPLETED
        assert run.status == RunStatus.RUNNING.value
        assert run.article_markdown is None
