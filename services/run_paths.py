import re
from pathlib import Path

from services.markdown import safe_stem


RUNS_ROOT = Path("runs")
PUBLISHED_IMAGES_ROOT = Path("images")

_RUN_ID_RE = re.compile(r"^[a-f0-9]{32}$")


def _validate_run_id(run_id: str) -> None:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(f"Invalid run_id: {run_id!r}")


def _validate_image_filename(filename: str) -> None:
    path = Path(filename)

    if not filename or filename in {".", ".."} or path.name != filename:
        raise ValueError(f"Invalid image filename: {filename!r}")


def run_dir(run_id: str) -> Path:
    _validate_run_id(run_id)
    return RUNS_ROOT / run_id


def run_images_dir(run_id: str) -> Path:
    return run_dir(run_id) / "images"


def staged_image_path(
    *,
    run_id: str,
    filename: str,
) -> Path:
    _validate_image_filename(filename)

    return run_images_dir(run_id) / filename


def published_images_dir(
    *,
    title: str,
    run_id: str,
) -> Path:
    _validate_run_id(run_id)

    article_stem = safe_stem(title)

    if not article_stem:
        raise ValueError("Cannot build image path from an empty article title.")

    return PUBLISHED_IMAGES_ROOT / article_stem / run_id


def published_image_path(
    *,
    title: str,
    run_id: str,
    filename: str,
) -> Path:
    _validate_image_filename(filename)

    return (
        published_images_dir(
            title=title,
            run_id=run_id,
        )
        / filename
    )


def markdown_image_path(
    *,
    title: str,
    run_id: str,
    filename: str,
) -> str:
    published = published_image_path(
        title=title,
        run_id=run_id,
        filename=filename,
    )

    return f"../{published.as_posix()}"
