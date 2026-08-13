import re


HEADING_PATTERN = re.compile(
    r"^(#{1,6})\s+(.+?)\s*$",
    re.MULTILINE,
)


def repair_heading_structure(
    markdown: str,
) -> str:
    """
    Enforce:

    # Title
    ## Section
    ## Section
    ## Section
    """

    headings = list(HEADING_PATTERN.finditer(markdown))

    if not headings:
        return markdown

    result_parts: list[str] = []

    cursor = 0
    h1_seen = False

    for match in headings:
        result_parts.append(markdown[cursor : match.start()])

        hashes = match.group(1)
        title = match.group(2).strip()

        if not h1_seen:
            new_heading = f"# {title}"
            h1_seen = True
        else:
            new_heading = f"## {title}"

        result_parts.append(new_heading)

        cursor = match.end()

    result_parts.append(markdown[cursor:])

    return "".join(result_parts)
