import os
import shutil
from pathlib import Path
from uuid import uuid4

from services.markdown import (
    safe_blog_filename,
)
from services.run_paths import (
    published_images_dir,
    run_images_dir,
)


def _temporary_sibling(
    destination: Path,
) -> Path:
    return destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")


def _atomic_copy_file(
    source: Path,
    destination: Path,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = _temporary_sibling(destination)

    try:
        shutil.copyfile(
            source,
            temporary,
        )

        os.replace(
            temporary,
            destination,
        )

    finally:
        temporary.unlink(
            missing_ok=True,
        )


def _atomic_write_text(
    destination: Path,
    text: str,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = _temporary_sibling(destination)

    try:
        temporary.write_text(
            text,
            encoding="utf-8",
        )

        os.replace(
            temporary,
            destination,
        )

    finally:
        temporary.unlink(
            missing_ok=True,
        )


def publish_blog(
    *,
    title: str,
    markdown: str,
    run_id: str,
    image_results: list[dict],
) -> Path:
    if not markdown.strip():
        raise ValueError("Cannot publish empty Markdown.")

    expected_stage_dir = run_images_dir(run_id).resolve()

    expected_publish_dir = published_images_dir(
        title=title,
        run_id=run_id,
    ).resolve()

    prepared_images: list[tuple[Path, Path]] = []

    # Validate every source/destination before
    # publishing anything.
    for result in image_results:
        if result["status"] != "inserted":
            raise RuntimeError(
                f"Cannot publish image {result['id']} because it was not inserted."
            )

        source = Path(result["staged_path"]).resolve()

        destination = Path(result["published_path"]).resolve()

        if source.parent != expected_stage_dir:
            raise ValueError(
                f"Staged image path is outside this run: {result['staged_path']}"
            )

        if destination.parent != expected_publish_dir:
            raise ValueError(
                "Published image path is outside "
                "this article/run: "
                f"{result['published_path']}"
            )

        markdown_destination = (
            Path("generated_blogs") / result["markdown_path"]
        ).resolve()

        if destination != markdown_destination:
            raise ValueError(
                "Published image path does not "
                "match Markdown path for image "
                f"{result['id']}."
            )

        if not source.is_file():
            raise FileNotFoundError(f"Staged image does not exist: {source}")

        if source.stat().st_size == 0:
            raise RuntimeError(f"Staged image is empty: {source}")

        prepared_images.append(
            (
                source,
                destination,
            )
        )

    # Publish images first.
    #
    # If image publishing fails, the final
    # Markdown file is never replaced.
    for (
        source,
        destination,
    ) in prepared_images:
        _atomic_copy_file(
            source,
            destination,
        )

    blog_path = Path("generated_blogs") / safe_blog_filename(title)

    # Markdown replacement is the final
    # successful publish point.
    _atomic_write_text(
        blog_path,
        markdown,
    )

    return blog_path
