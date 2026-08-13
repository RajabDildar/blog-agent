import re
from collections.abc import Sequence


HEADING_PATTERN = re.compile(
    r"^(#{1,6})\s+(.+?)\s*$",
    re.MULTILINE,
)


def validate_article_markdown(
    markdown: str,
    *,
    expected_sections: Sequence[str],
) -> list[str]:
    errors: list[str] = []

    if not markdown.strip():
        return ["Article Markdown is empty."]

    headings = HEADING_PATTERN.findall(markdown)

    h1s = [title.strip() for level, title in headings if level == "#"]

    if len(h1s) != 1:
        errors.append(f"Expected exactly one H1, found {len(h1s)}.")

    if h1s:
        if not markdown.startswith(f"# {h1s[0]}"):
            errors.append("Document must begin with its H1 title.")

    for level, title in headings:
        if len(level) > 2:
            errors.append(f"Invalid heading level found: {level} {title}")

    actual_h2s = [title.strip() for level, title in headings if level == "##"]

    if not actual_h2s:
        errors.append("No H2 sections found.")

    expected = list(expected_sections)

    if actual_h2s != expected:
        errors.append("Article sections do not match the planned section order.")

        # Give useful detail.
        for index, expected_title in enumerate(expected):
            actual_title = actual_h2s[index] if index < len(actual_h2s) else None

            if actual_title != expected_title:
                errors.append(
                    f"Section {index + 1}: expected "
                    f"'{expected_title}', got "
                    f"'{actual_title}'."
                )

    code_fences = re.findall(
        r"```",
        markdown,
    )

    if len(code_fences) % 2 != 0:
        errors.append("Unclosed Markdown code fence.")

    forbidden_markers = {
        "[[IMAGE_": ("Unresolved image placeholder."),
        "IMAGE GENERATION FAILED": ("Image failure text leaked into output."),
        "Not found in provided sources.": (
            "Unsupported claim marker leaked into output."
        ),
    }

    for marker, error in forbidden_markers.items():
        if marker in markdown:
            errors.append(error)

    return errors
