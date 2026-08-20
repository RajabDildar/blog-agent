from pathlib import Path

from services.final_validation import validate_final_images
from services.run_paths import (
    markdown_image_path,
    published_image_path,
    staged_image_path,
)

RUN_ID = "d" * 32
TITLE = "Final Validation"


def inserted_result(
    filename: str = "architecture.png",
    *,
    image_id: str = "img-1",
) -> dict:
    return {
        "id": image_id,
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


def create_staged_image(result: dict) -> None:
    path = Path(result["staged_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"image")


def test_valid_generated_image_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = inserted_result()
    create_staged_image(result)

    markdown = (
        "# Final Validation\n\n"
        "## Architecture\n\n"
        f"![Architecture]({result['markdown_path']})\n"
    )

    errors = validate_final_images(
        markdown,
        image_results=[result],
    )

    assert errors == []


def test_generated_image_is_validated_from_staging_before_publish(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    result = inserted_result()
    create_staged_image(result)

    # The final image has not been published yet.
    assert not Path(result["published_path"]).exists()

    markdown = f"# Final Validation\n\n![Architecture]({result['markdown_path']})\n"

    assert (
        validate_final_images(
            markdown,
            image_results=[result],
        )
        == []
    )


def test_missing_staged_image_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = inserted_result()

    markdown = f"# Final Validation\n\n![Architecture]({result['markdown_path']})\n"

    errors = validate_final_images(
        markdown,
        image_results=[result],
    )

    assert any("Staged generated image does not exist" in error for error in errors)


def test_missing_generated_image_reference_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = inserted_result()
    create_staged_image(result)

    errors = validate_final_images(
        "# Final Validation\n\nNo image here.\n",
        image_results=[result],
    )

    assert f"Generated image is not embedded: {result['markdown_path']}" in errors


def test_duplicate_generated_image_reference_fails(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    result = inserted_result()
    create_staged_image(result)

    markdown = (
        "# Final Validation\n\n"
        f"![First]({result['markdown_path']})\n\n"
        "More content.\n\n"
        f"![Duplicate]({result['markdown_path']})\n"
    )

    errors = validate_final_images(
        markdown,
        image_results=[result],
    )

    assert any(
        "Generated image is embedded multiple times" in error for error in errors
    )


def test_duplicate_image_results_using_same_markdown_path_fail(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    first = inserted_result(
        "shared.png",
        image_id="img-1",
    )
    second = dict(first)
    second["id"] = "img-2"

    create_staged_image(first)

    markdown = f"# Final Validation\n\n![Shared]({first['markdown_path']})\n"

    errors = validate_final_images(
        markdown,
        image_results=[first, second],
    )

    assert any(
        "Multiple generated images use the same Markdown path" in error
        for error in errors
    )


def test_published_path_must_match_markdown_destination(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    result = inserted_result()
    create_staged_image(result)
    result["published_path"] = "images/wrong/place.png"

    markdown = f"# Final Validation\n\n![Architecture]({result['markdown_path']})\n"

    errors = validate_final_images(
        markdown,
        image_results=[result],
    )

    assert any(
        "Published image path does not match Markdown path" in error for error in errors
    )


def test_image_like_syntax_inside_code_does_not_count_as_embedding(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    result = inserted_result()
    create_staged_image(result)

    markdown = f"""# Final Validation

```markdown
![Example]({result["markdown_path"]})
```
"""

    errors = validate_final_images(
        markdown,
        image_results=[result],
    )

    assert f"Generated image is not embedded: {result['markdown_path']}" in errors


def test_unknown_missing_local_image_reference_fails(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    markdown = """# Final Validation

![Unknown](../images/unknown.png)
"""

    errors = validate_final_images(
        markdown,
        image_results=[],
    )

    assert "Referenced image does not exist: ../images/unknown.png" in errors


def test_external_image_does_not_require_local_file(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    markdown = """# Final Validation

![External](https://example.com/architecture.png)
"""

    assert (
        validate_final_images(
            markdown,
            image_results=[],
        )
        == []
    )


def test_non_inserted_image_result_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = inserted_result()
    result["status"] = "failed"

    errors = validate_final_images(
        "# Final Validation\n",
        image_results=[result],
    )

    assert "Image img-1 was not inserted." in errors
