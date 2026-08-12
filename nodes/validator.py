import re

from schemas.state import State
from services.image_validation import (
    validate_image_references,
)


HEADING_PATTERN = re.compile(
    r"^(#{1,6})\s+(.+?)\s*$",
    re.MULTILINE,
)


def validate_markdown(
    markdown: str,
    *,
    expected_sections: list[str],
    image_results: list[dict],
) -> list[str]:
    errors: list[str] = []

    if not markdown.strip():
        errors.append("Final Markdown is empty.")

        return errors

    headings = HEADING_PATTERN.findall(markdown)

    h1s = [title for level, title in headings if level == "#"]

    if len(h1s) != 1:
        errors.append(f"Expected exactly one H1, found {len(h1s)}.")

    if h1s and not markdown.startswith(f"# {h1s[0]}"):
        errors.append("Document must begin with its H1 title.")

    for level, title in headings:
        if len(level) > 2:
            errors.append(f"Invalid heading level found: {level} {title}")

    actual_h2s = [title.strip() for level, title in headings if level == "##"]

    if not actual_h2s:
        errors.append("No H2 sections found.")

    expected_index = 0

    for title in actual_h2s:
        if (
            expected_index < len(expected_sections)
            and title == expected_sections[expected_index]
        ):
            expected_index += 1

    if expected_index != len(expected_sections):
        missing = expected_sections[expected_index:]

        errors.append("Missing or incorrectly ordered sections: " + ", ".join(missing))

    code_fences = re.findall(
        r"```",
        markdown,
    )

    if len(code_fences) % 2 != 0:
        errors.append("Unclosed Markdown code fence.")

    forbidden_markers = {
        "[[IMAGE_": "Unresolved image placeholder.",
        "IMAGE GENERATION FAILED": ("Image failure text leaked into output."),
        "Not found in provided sources.": (
            "Unsupported claim marker leaked into output."
        ),
    }

    for marker, error in forbidden_markers.items():
        if marker in markdown:
            errors.append(error)

    errors.extend(
        validate_image_references(
            markdown,
            image_results,
        )
    )

    return errors


def validator_node(state: State) -> dict:
    plan = state["plan"]

    if plan is None:
        raise ValueError("Validator: plan is missing.")

    expected_sections = [task.title for task in plan.tasks]

    errors = validate_markdown(
        state["final"],
        expected_sections=expected_sections,
        image_results=state.get(
            "image_results",
            [],
        ),
    )

    return {
        "validation_errors": errors,
        "validation_passed": not errors,
    }
