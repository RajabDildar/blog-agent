from collections.abc import Sequence

from services.markdown_parser import (
    contains_text_outside_code,
    find_unclosed_fence,
    get_headings,
)


FORBIDDEN_MARKERS = {
    "[[IMAGE_": "Unresolved image placeholder.",
    "IMAGE GENERATION FAILED": "Image failure text leaked into output.",
    "Not found in provided sources.": "Unsupported claim marker leaked into output.",
}


def validate_article_markdown(
    markdown: str,
    *,
    expected_title: str,
    expected_sections: Sequence[str],
) -> list[str]:
    errors: list[str] = []

    if not markdown.strip():
        return ["Article Markdown is empty."]

    headings = get_headings(markdown)

    h1s = [heading for heading in headings if heading.level == 1]

    if len(h1s) != 1:
        errors.append(f"Expected exactly one H1, found {len(h1s)}.")

    elif h1s[0].text != expected_title.strip():
        errors.append(f"Expected H1 '# {expected_title}', got '# {h1s[0].text}'.")

    first_nonempty_line = next(
        (line.strip() for line in markdown.splitlines() if line.strip()),
        "",
    )

    expected_h1 = f"# {expected_title.strip()}"

    if first_nonempty_line != expected_h1:
        errors.append("Document must begin with the planned H1 title.")

    actual_h2s = [heading.text for heading in headings if heading.level == 2]

    expected_h2s = [section.strip() for section in expected_sections]

    if actual_h2s != expected_h2s:
        errors.append("Article sections do not match the planned section order.")

        max_length = max(
            len(actual_h2s),
            len(expected_h2s),
        )

        for index in range(max_length):
            expected_at_index = (
                expected_h2s[index] if index < len(expected_h2s) else None
            )

            actual_at_index = actual_h2s[index] if index < len(actual_h2s) else None

            if actual_at_index != expected_at_index:
                errors.append(
                    f"Section {index + 1}: "
                    f"expected "
                    f"'{expected_at_index}', "
                    f"got "
                    f"'{actual_at_index}'."
                )

    unclosed_fence_line = find_unclosed_fence(markdown)

    if unclosed_fence_line is not None:
        errors.append(
            f"Unclosed Markdown code fence starting on line {unclosed_fence_line}."
        )

    for marker, error in FORBIDDEN_MARKERS.items():
        if contains_text_outside_code(
            markdown,
            marker,
        ):
            errors.append(error)

    return errors
