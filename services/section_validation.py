import re


def validate_section_markdown(
    markdown: str,
    *,
    expected_title: str,
) -> list[str]:
    errors: list[str] = []

    if not markdown.strip():
        return ["Section Markdown is empty."]

    headings = re.findall(
        r"^(#{1,6})\s+(.+?)\s*$",
        markdown,
        re.MULTILINE,
    )

    if len(headings) != 1:
        errors.append("Section must contain exactly one heading.")
    else:
        level, title = headings[0]

        if level != "##":
            errors.append("Section heading must be H2.")

        if title.strip() != expected_title.strip():
            errors.append(f"Expected heading '## {expected_title}', got '## {title}'.")

    code_fences = re.findall(
        r"```",
        markdown,
    )

    if len(code_fences) % 2 != 0:
        errors.append("Section contains an unclosed code fence.")

    return errors
