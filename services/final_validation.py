from collections import Counter
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
    reference_counts = Counter(references)

    inserted_results = [
        result for result in image_results if result["status"] == "inserted"
    ]

    expected_counts = Counter(result["markdown_path"] for result in inserted_results)

    # Every successfully generated image path should be unique
    # and embedded exactly once.
    for path, expected_count in expected_counts.items():
        if expected_count > 1:
            errors.append(
                f"Multiple generated images use the same Markdown path: {path}"
            )

        actual_count = reference_counts[path]

        if actual_count == 0:
            errors.append(f"Generated image is not embedded: {path}")
        elif actual_count > 1:
            errors.append(
                f"Generated image is embedded multiple times: {path}"
                f" (count={actual_count})"
            )

    # Every local image reference in the final Markdown must exist.
    for path in reference_counts:
        if path.startswith(
            (
                "http://",
                "https://",
            )
        ):
            continue

        filesystem_path = (Path("generated_blogs") / path).resolve()

        if not filesystem_path.exists():
            errors.append(f"Referenced image does not exist: {path}")

    # Any image that failed before insertion makes the final artifact invalid.
    for result in image_results:
        if result["status"] != "inserted":
            errors.append(f"Image {result['id']} was not inserted.")

    return errors
