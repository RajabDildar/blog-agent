"""Unit tests for article storage, excerpt extraction, asset route conversion, and dual storage backend."""
import pytest
from pathlib import Path
from unittest.mock import patch

from blog_agent.services.run_paths import (
    markdown_image_path,
    published_image_path,
    staged_image_path,
)
from blog_agent.services.storage import (
    extract_article_excerpt,
    publish_blog,
    convert_markdown_asset_routes,
)


def test_extract_article_excerpt_normal():
    md = """# My Blog Title

This is the first plain-text paragraph of the technical article. It explains the main concepts cleanly.

## Section 1

Another paragraph here.
"""
    excerpt = extract_article_excerpt(md)
    assert excerpt == "This is the first plain-text paragraph of the technical article. It explains the main concepts cleanly."


def test_extract_article_excerpt_fallback():
    md = "# Title Only\n\n```python\nprint('hello')\n```\n"
    excerpt = extract_article_excerpt(md)
    assert isinstance(excerpt, str)


def test_publish_blog_empty_markdown():
    with pytest.raises(ValueError, match="Cannot publish empty Markdown"):
        publish_blog(title="Test", markdown="", run_id="a" * 32, image_results=[])


def test_publish_blog_local_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_id = "a" * 32
    title = "Test Article"

    staged_img = staged_image_path(run_id=run_id, filename="diagram.png")
    staged_img.parent.mkdir(parents=True, exist_ok=True)
    staged_img.write_bytes(b"image-content-data")

    pub_img = published_image_path(title=title, run_id=run_id, filename="diagram.png")
    md_img_path = markdown_image_path(title=title, run_id=run_id, filename="diagram.png")

    image_results = [
        {
            "id": "img_1",
            "filename": "diagram.png",
            "staged_path": str(staged_img),
            "published_path": str(pub_img),
            "markdown_path": str(md_img_path),
            "status": "inserted",
        }
    ]

    md_content = f"# Test Article\n\n![Diagram]({md_img_path})\n\nContent paragraph."

    blog_path = publish_blog(
        title=title,
        markdown=md_content,
        run_id=run_id,
        image_results=image_results,
    )

    assert blog_path.is_file()
    saved_text = blog_path.read_text(encoding="utf-8")
    assert saved_text == md_content

    # Asset route conversion for web API / PostgreSQL
    converted = convert_markdown_asset_routes(md_content, run_id, image_results)
    assert f"/articles/{run_id}/assets/diagram.png" in converted


def test_cleanup_expired_runs():
    from datetime import datetime, timezone, timedelta
    from unittest.mock import MagicMock
    from apps.api.db.models import Run, RunStatus
    from apps.api.maintenance.cleanup_expired_runs import cleanup_expired_runs

    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=50)

    anon_run = Run(
        id="anon-exp-1",
        original_input="Expired input",
        anonymous_session_id="anon-cookie-1",
        created_at=old_time,
        status=RunStatus.COMPLETED.value,
        article_markdown="# Expired Content",
        article_assets=[
            {"filename": "img1.png", "public_id": "blog-agent/runs/anon-exp-1/images/img1"},
            {"filename": "local.png", "public_id": "local:anon-exp-1:local.png"},
        ],
    )

    claimed_run = Run(
        id="claimed-run-1",
        user_id="user-123",
        original_input="Claimed input",
        anonymous_session_id=None,
        created_at=old_time,
        status=RunStatus.COMPLETED.value,
        article_markdown="# Claimed Content",
        article_assets=[{"filename": "img2.png", "public_id": "blog-agent/runs/claimed-run-1/images/img2"}],
    )

    mock_session = MagicMock()
    mock_session.scalars.return_value.all.return_value = [anon_run]

    with patch("apps.api.maintenance.cleanup_expired_runs.WorkerSessionLocal") as mock_ws:
        mock_ws.return_value.__enter__.return_value = mock_session
        with patch("blog_agent.services.cloudinary_storage.delete_cloudinary_assets") as mock_del:
            count = cleanup_expired_runs(retention_hours=48)

            assert count == 1
            assert anon_run.status == RunStatus.EXPIRED.value
            assert anon_run.article_markdown is None
            assert anon_run.article_assets is None
            mock_del.assert_called_once_with(["blog-agent/runs/anon-exp-1/images/img1"])
