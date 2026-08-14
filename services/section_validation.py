from services.markdown_parser import (
    find_unclosed_fence,
    get_headings,
)


def validate_section_markdown(
    markdown: str,
) -> list[str]:
    errors: list[str] = []

    if not markdown.strip():
        return ["Section Markdown is empty."]

    for heading in get_headings(markdown):
        if heading.level <= 2:
            errors.append(
                f"Section body cannot contain H{heading.level}: "
                f"'{heading.text}' on line {heading.line}."
            )

    unclosed_fence_line = find_unclosed_fence(markdown)

    if unclosed_fence_line is not None:
        errors.append(
            "Section contains an unclosed code fence "
            f"starting on line {unclosed_fence_line}."
        )

    return errors
