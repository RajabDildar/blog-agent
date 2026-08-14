from dataclasses import dataclass
import re

from markdown_it import MarkdownIt
from markdown_it.token import Token


PARSER = MarkdownIt("gfm-like2", {"html": True})


FENCE_LINE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


@dataclass(frozen=True, slots=True)
class Heading:
    level: int
    text: str
    line: int


def parse_markdown(markdown: str) -> list[Token]:
    return PARSER.parse(markdown)


def get_headings(markdown: str) -> list[Heading]:
    tokens = parse_markdown(markdown)

    headings: list[Heading] = []

    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue

        inline_token = tokens[index + 1] if index + 1 < len(tokens) else None

        text = (
            inline_token.content.strip()
            if inline_token is not None and inline_token.type == "inline"
            else ""
        )

        line = token.map[0] + 1 if token.map else 1

        headings.append(
            Heading(
                level=int(token.tag.removeprefix("h")),
                text=text,
                line=line,
            )
        )

    return headings


def get_image_sources(markdown: str) -> list[str]:
    sources: list[str] = []

    for token in parse_markdown(markdown):
        for child in token.children or []:
            if child.type != "image":
                continue

            src = child.attrGet("src")

            if isinstance(src, str):
                sources.append(src)

    return sources


def has_gfm_table(markdown: str) -> bool:
    return any(token.type == "table_open" for token in parse_markdown(markdown))


def has_fenced_code(markdown: str) -> bool:
    return any(token.type == "fence" for token in parse_markdown(markdown))


def find_unclosed_fence(markdown: str) -> int | None:
    """
    Project-level truncation check.

    CommonMark can parse a fence that reaches EOF without an explicit
    closing marker. For generated content we deliberately flag that
    situation because it commonly indicates truncated LLM output.
    """

    open_char: str | None = None
    open_length = 0
    open_line = 0

    for line_number, line in enumerate(
        markdown.splitlines(),
        start=1,
    ):
        match = FENCE_LINE_RE.match(line)

        if not match:
            continue

        marker = match.group(1)
        rest = match.group(2)

        marker_char = marker[0]
        marker_length = len(marker)

        if open_char is None:
            # Backtick fence info strings cannot contain backticks.
            if marker_char == "`" and "`" in rest:
                continue

            open_char = marker_char
            open_length = marker_length
            open_line = line_number
            continue

        is_matching_close = (
            marker_char == open_char
            and marker_length >= open_length
            and not rest.strip()
        )

        if is_matching_close:
            open_char = None
            open_length = 0
            open_line = 0

    return open_line or None
