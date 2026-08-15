\
from pathlib import Path

from services.final_validation import validate_final_images


def inserted_result(
    path: str = "../images/architecture.png",
    *,
    image_id: str = "img-1",
) -> dict:
    return {
        "id": image_id,
        "filename": Path(path).name,
        "markdown_path": path,
        "section_id": 1,
        "status": "inserted",
    }


def test_valid_generated_image_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "architecture.png").write_bytes(b"image")

    markdown = """# Blog

## Architecture

![Architecture](../images/architecture.png)
"""

    errors = validate_final_images(
        markdown,
        image_results=[inserted_result()],
    )

    assert errors == []


def test_missing_generated_image_reference_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    errors = validate_final_images(
        "# Blog\n\n## Architecture\n\nNo image here.\n",
        image_results=[inserted_result()],
    )

    assert "Generated image is not embedded: ../images/architecture.png" in errors


def test_duplicate_generated_image_reference_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "architecture.png").write_bytes(b"image")

    markdown = """# Blog

## Architecture

![First](../images/architecture.png)

More content.

![Duplicate](../images/architecture.png)
"""

    errors = validate_final_images(
        markdown,
        image_results=[inserted_result()],
    )

    assert any(
        "Generated image is embedded multiple times: ../images/architecture.png"
        in error
        for error in errors
    )


def test_duplicate_image_results_using_same_path_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "shared.png").write_bytes(b"image")

    markdown = """# Blog

## Architecture

![Shared](../images/shared.png)
"""

    errors = validate_final_images(
        markdown,
        image_results=[
            inserted_result("../images/shared.png", image_id="img-1"),
            inserted_result("../images/shared.png", image_id="img-2"),
        ],
    )

    assert any(
        "Multiple generated images use the same Markdown path: ../images/shared.png"
        in error
        for error in errors
    )


def test_image_like_syntax_inside_code_does_not_count_as_embedding(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    markdown = """# Blog

## Architecture

```markdown
![Example](../images/architecture.png)
```
"""

    errors = validate_final_images(
        markdown,
        image_results=[inserted_result()],
    )

    assert "Generated image is not embedded: ../images/architecture.png" in errors


def test_missing_local_image_file_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    markdown = """# Blog

## Architecture

![Architecture](../images/architecture.png)
"""

    errors = validate_final_images(
        markdown,
        image_results=[inserted_result()],
    )

    assert "Referenced image does not exist: ../images/architecture.png" in errors


def test_external_image_does_not_require_local_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    markdown = """# Blog

## Architecture

![External](https://example.com/architecture.png)
"""

    errors = validate_final_images(
        markdown,
        image_results=[],
    )

    assert errors == []


def test_non_inserted_image_result_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = inserted_result()
    result["status"] = "failed"

    errors = validate_final_images(
        "# Blog\n",
        image_results=[result],
    )

    assert "Image img-1 was not inserted." in errors
