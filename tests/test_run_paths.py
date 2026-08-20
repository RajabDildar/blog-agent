from pathlib import Path

import pytest

from services.run_paths import (
    markdown_image_path,
    published_image_path,
    published_images_dir,
    run_images_dir,
    staged_image_path,
)

RUN_ID = "a" * 32


def test_run_images_are_isolated_by_run_id():
    assert run_images_dir(RUN_ID) == Path("runs") / RUN_ID / "images"


def test_staged_image_path_is_inside_run_directory():
    assert (
        staged_image_path(
            run_id=RUN_ID,
            filename="architecture.png",
        )
        == Path("runs") / RUN_ID / "images" / "architecture.png"
    )


def test_published_images_are_isolated_by_article_and_run():
    assert published_images_dir(
        title="AI Fraud Detection",
        run_id=RUN_ID,
    ) == (Path("images") / "ai_fraud_detection" / RUN_ID)


def test_published_and_markdown_paths_point_to_same_final_image():
    published = published_image_path(
        title="AI Fraud Detection",
        run_id=RUN_ID,
        filename="architecture.png",
    )

    markdown = markdown_image_path(
        title="AI Fraud Detection",
        run_id=RUN_ID,
        filename="architecture.png",
    )

    assert published == (
        Path("images") / "ai_fraud_detection" / RUN_ID / "architecture.png"
    )
    assert markdown == (f"../images/ai_fraud_detection/{RUN_ID}/architecture.png")


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        "short",
        "../escape",
        "A" * 32,
        "g" * 32,
    ],
)
def test_invalid_run_ids_are_rejected(run_id):
    with pytest.raises(ValueError, match="Invalid run_id"):
        run_images_dir(run_id)


@pytest.mark.parametrize(
    "filename",
    [
        "",
        "../image.png",
        "nested/image.png",
        ".",
        "..",
    ],
)
def test_unsafe_image_filenames_are_rejected(filename):
    with pytest.raises(ValueError, match="Invalid image filename"):
        staged_image_path(
            run_id=RUN_ID,
            filename=filename,
        )
