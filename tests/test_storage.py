from pathlib import Path

import pytest

from services.run_paths import (
    markdown_image_path,
    published_image_path,
    staged_image_path,
)
from services.storage import publish_blog


RUN_ID = "c" * 32
TITLE = "Run Isolation"


def make_inserted_result(filename: str = "architecture.png") -> dict:
    return {
        "id": "img-1",
        "filename": filename,
        "markdown_path": markdown_image_path(
            title=TITLE,
            run_id=RUN_ID,
            filename=filename,
        ),
        "staged_path": str(
            staged_image_path(
                run_id=RUN_ID,
                filename=filename,
            )
        ),
        "published_path": str(
            published_image_path(
                title=TITLE,
                run_id=RUN_ID,
                filename=filename,
            )
        ),
        "section_id": 1,
        "status": "inserted",
    }


def test_publish_blog_copies_images_then_writes_final_markdown(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    result = make_inserted_result()
    staged = Path(result["staged_path"])
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"image-bytes")

    markdown = (
        "# Run Isolation\n\n"
        "## Architecture\n\n"
        f"![Architecture]({result['markdown_path']})\n"
    )

    blog_path = publish_blog(
        title=TITLE,
        markdown=markdown,
        run_id=RUN_ID,
        image_results=[result],
    )

    assert blog_path == Path("generated_blogs/run_isolation.md")
    assert blog_path.read_text(encoding="utf-8") == markdown

    published = Path(result["published_path"])
    assert published.read_bytes() == b"image-bytes"

    # Publishing copies from staging so the run remains available
    # for diagnostics/checkpoint work.
    assert staged.read_bytes() == b"image-bytes"


def test_publish_replaces_existing_blog_file(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    blog_dir = tmp_path / "generated_blogs"
    blog_dir.mkdir()
    old_blog = blog_dir / "run_isolation.md"
    old_blog.write_text("old content", encoding="utf-8")

    new_markdown = "# Run Isolation\n\nNew content.\n"

    blog_path = publish_blog(
        title=TITLE,
        markdown=new_markdown,
        run_id=RUN_ID,
        image_results=[],
    )

    assert blog_path.read_text(encoding="utf-8") == new_markdown
    assert not list(blog_dir.glob("*.tmp"))


def test_missing_staged_image_prevents_any_publish(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    first = make_inserted_result("first.png")
    second = make_inserted_result("missing.png")

    first_staged = Path(first["staged_path"])
    first_staged.parent.mkdir(parents=True)
    first_staged.write_bytes(b"first-image")

    with pytest.raises(
        FileNotFoundError,
        match="Staged image does not exist",
    ):
        publish_blog(
            title=TITLE,
            markdown="# Run Isolation\n",
            run_id=RUN_ID,
            image_results=[first, second],
        )

    assert not Path(first["published_path"]).exists()
    assert not Path(second["published_path"]).exists()
    assert not Path("generated_blogs/run_isolation.md").exists()


def test_empty_staged_image_prevents_publish(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    result = make_inserted_result()
    staged = Path(result["staged_path"])
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"")

    with pytest.raises(
        RuntimeError,
        match="Staged image is empty",
    ):
        publish_blog(
            title=TITLE,
            markdown="# Run Isolation\n",
            run_id=RUN_ID,
            image_results=[result],
        )

    assert not Path(result["published_path"]).exists()
    assert not Path("generated_blogs/run_isolation.md").exists()


def test_mismatched_published_path_is_rejected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    result = make_inserted_result()
    staged = Path(result["staged_path"])
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"image")

    result["published_path"] = "images/wrong/place.png"

    with pytest.raises(
        ValueError,
        match="Published image path is outside",
    ):
        publish_blog(
            title=TITLE,
            markdown="# Run Isolation\n",
            run_id=RUN_ID,
            image_results=[result],
        )
