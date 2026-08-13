import re


HEADING_PATTERN = re.compile(
    r"^(#{1,6})\s+(.+?)\s*$",
    re.MULTILINE,
)


def repair_heading_structure(
    markdown: str,
) -> str:
    headings = list(HEADING_PATTERN.finditer(markdown))

    if not headings:
        return markdown

    parts: list[str] = []

    cursor = 0

    for index, match in enumerate(headings):
        parts.append(markdown[cursor : match.start()])

        title = match.group(2).strip()

        if index == 0:
            new_heading = f"# {title}"
        else:
            new_heading = f"## {title}"

        parts.append(new_heading)

        cursor = match.end()

    parts.append(markdown[cursor:])

    return "".join(parts)
