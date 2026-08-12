import re
from pathlib import Path


IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def validate_image_references(
    markdown: str,
    image_results: list[dict],
) -> list[str]:
    errors: list[str] = []

    references = IMAGE_PATTERN.findall(markdown)

    expected_paths = {
        result["markdown_path"]
        for result in image_results
        if result["status"] == "inserted"
    }

    actual_paths = set(references)

    for path in expected_paths:
        if path not in actual_paths:
            errors.append(f"Generated image is not referenced: {path}")

    for path in actual_paths:
        if path.startswith(("http://", "https://")):
            continue

        resolved = (Path("generated_blogs") / path).resolve()

        if not resolved.exists():
            errors.append(f"Referenced image does not exist: {path}")

    for result in image_results:
        if result["status"] != "inserted":
            errors.append(f"Image {result['id']} was not inserted.")

    return errors
