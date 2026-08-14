from pathlib import Path

from services.markdown_parser import (
    get_image_sources,
)


def validate_final_images(
    markdown: str,
    *,
    image_results: list[dict],
) -> list[str]:
    errors: list[str] = []

    references = get_image_sources(markdown)

    expected_paths = {
        result["markdown_path"]
        for result in image_results
        if result["status"] == "inserted"
    }

    actual_paths = set(references)

    for path in expected_paths:
        if path not in actual_paths:
            errors.append(f"Generated image is not embedded: {path}")

    for path in actual_paths:
        if path.startswith(("http://", "https://")):
            continue

        filesystem_path = (Path("generated_blogs") / path).resolve()

        if not filesystem_path.exists():
            errors.append(f"Referenced image does not exist: {path}")

    for result in image_results:
        if result["status"] != "inserted":
            errors.append(f"Image {result['id']} was not inserted.")

    return errors
