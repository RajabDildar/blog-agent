import re
from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class SectionBounds:
    heading_start_line: int
    heading_end_line: int
    section_end_line: int


TOP_LEVEL_BODY_TYPES = {
    "paragraph_open",
    "fence",
    "code_block",
    "blockquote_open",
    "bullet_list_open",
    "ordered_list_open",
    "table_open",
    "html_block",
    "hr",
}


def find_h2_section_bounds(
    markdown: str,
    section_title: str,
) -> SectionBounds:
    tokens = parse_markdown(markdown)

    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.tag != "h2":
            continue

        inline = tokens[index + 1] if index + 1 < len(tokens) else None

        if inline is None or inline.type != "inline":
            continue

        if inline.content.strip() != section_title.strip():
            continue

        if token.map is None:
            break

        section_end_line = len(markdown.splitlines())

        for next_token in tokens[index + 1 :]:
            if (
                next_token.type == "heading_open"
                and next_token.tag == "h2"
                and next_token.map is not None
            ):
                section_end_line = next_token.map[0]
                break

        return SectionBounds(
            heading_start_line=(token.map[0]),
            heading_end_line=(token.map[1]),
            section_end_line=(section_end_line),
        )

    raise ValueError(f"Section not found for image insertion: {section_title}")


def find_first_body_block_end(
    markdown: str,
    *,
    start_line: int,
    end_line: int,
) -> int:
    for token in parse_markdown(markdown):
        if token.level != 0 or token.map is None:
            continue

        token_start, token_end = token.map

        if token_start < start_line or token_start >= end_line:
            continue

        if token.type in TOP_LEVEL_BODY_TYPES:
            return min(
                token_end,
                end_line,
            )

    return start_line


def contains_text_outside_code(
    markdown: str,
    needle: str,
) -> bool:
    """
    Return True when `needle` appears in Markdown content outside
    fenced/block code and inline code.

    Markdown structure is determined by markdown-it-py tokens rather
    than by raw string scanning.
    """
    for token in parse_markdown(markdown):
        # Fenced and indented code are not article prose.
        if token.type in {
            "fence",
            "code_block",
        }:
            continue

        if token.type != "inline":
            if needle in token.content:
                return True

            continue

        for child in token.children or []:
            # Inline code is content, not article prose.
            if child.type == "code_inline":
                continue

            if needle in child.content:
                return True

    return False
