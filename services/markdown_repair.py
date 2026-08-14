import re

from services.markdown_format import (
    normalize_markdown,
)
from services.markdown_parser import (
    get_headings,
)


ATX_HEADING_RE = re.compile(
    r"^(?P<indent> {0,3})"
    r"(?P<marker>#{1,6})"
    r"[ \t]+"
    r"(?P<title>.*?)"
    r"[ \t]*#*[ \t]*$"
)


def strip_outer_markdown_fence(
    markdown: str,
) -> str:
    lines = markdown.splitlines()

    if len(lines) < 2:
        return markdown

    first = lines[0].strip().lower()
    last = lines[-1].strip()

    opening_to_closing = {
        "```markdown": "```",
        "```md": "```",
        "~~~markdown": "~~~",
        "~~~md": "~~~",
    }

    expected_closing = opening_to_closing.get(first)

    if expected_closing is None or last != expected_closing:
        return markdown

    return normalize_markdown("\n".join(lines[1:-1]))


def repair_section_structure(
    markdown: str,
    *,
    expected_title: str,
) -> str:
    repaired = strip_outer_markdown_fence(markdown)

    lines = repaired.splitlines()
    headings = get_headings(repaired)

    first_nonempty_index = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )

    for heading in headings:
        if heading.level > 2:
            continue

        line_index = heading.line - 1

        if line_index < 0 or line_index >= len(lines):
            continue

        match = ATX_HEADING_RE.match(lines[line_index])

        # Leave unusual/setext cases for LLM repair.
        if match is None:
            continue

        is_duplicated_section_heading = (
            line_index == first_nonempty_index
            and heading.text.strip() == expected_title.strip()
        )

        if is_duplicated_section_heading:
            lines[line_index] = ""
            continue

        # Any other H1/H2 inside a section body
        # becomes a subsection.
        lines[line_index] = f"{match.group('indent')}### {heading.text.strip()}"

    return normalize_markdown("\n".join(lines))


def repair_article_structure(
    markdown: str,
) -> str:
    # Article H1/H2 are application-owned.
    # Do not guess their intended structure here.
    return strip_outer_markdown_fence(markdown)
