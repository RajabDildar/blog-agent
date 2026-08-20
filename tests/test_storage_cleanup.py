from pathlib import Path

import pytest

from services.run_paths import (
    markdown_image_path,
    published_image_path,
    staged_image_path,
)
from services.storage import publish_blog

RUN_ID = "e" * 32
TITLE = "Storage Cleanup"


def make_inserted_result(filename: str) -> dict:
    return {
        "id": filename,
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


def test_partial_image_publish_is_cleaned_up(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    first = make_inserted_result("first.png")
    second = make_inserted_result("second.png")

    first_staged = Path(first["staged_path"])
    second_staged = Path(second["staged_path"])

    first_staged.parent.mkdir(parents=True)
    first_staged.write_bytes(b"first")
    second_staged.write_bytes(b"second")

    markdown = (
        "# Storage Cleanup\n\n"
        "## Architecture\n\n"
        f"![First]({first['markdown_path']})\n\n"
        f"![Second]({second['markdown_path']})\n"
    )

    original_atomic_copy_file = __import__(
        "services.storage",
        fromlist=["_atomic_copy_file"],
    )._atomic_copy_file

    calls = 0

    def fake_atomic_copy_file(source, destination):
        nonlocal calls
        calls += 1

        if calls == 2:
            raise OSError("simulated publish failure")

        return original_atomic_copy_file(source, destination)

    monkeypatch.setattr(
        "services.storage._atomic_copy_file",
        fake_atomic_copy_file,
    )

    with pytest.raises(OSError, match="simulated publish failure"):
        publish_blog(
            title=TITLE,
            markdown=markdown,
            run_id=RUN_ID,
            image_results=[first, second],
        )

    assert not Path(first["published_path"]).exists()
    assert not Path(second["published_path"]).exists()
    assert not Path("generated_blogs/storage_cleanup.md").exists()
