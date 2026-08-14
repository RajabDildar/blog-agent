import re

from schemas.models import ImageSpec
from services.markdown_parser import (
    find_first_body_block_end,
    find_h2_section_bounds,
    get_image_sources,
)


def safe_stem(value: str) -> str:
    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        "_",
        value,
    )

    return value.strip("_")


def safe_image_filename(
    value: str,
) -> str:
    return f"{safe_stem(value)}.png"


def safe_blog_filename(
    value: str,
) -> str:
    return f"{safe_stem(value)}.md"


def _line_to_offset(
    markdown: str,
    line_index: int,
) -> int:
    lines = markdown.splitlines(keepends=True)

    return sum(len(line) for line in lines[:line_index])


def _insert_at_line(
    markdown: str,
    *,
    line_index: int,
    image_md: str,
) -> str:
    offset = _line_to_offset(
        markdown,
        line_index,
    )

    before = markdown[:offset].rstrip("\n")

    after = markdown[offset:].lstrip("\n")

    parts = [
        part
        for part in (
            before,
            image_md,
            after,
        )
        if part
    ]

    return "\n\n".join(parts).rstrip() + "\n"


def insert_image(
    *,
    markdown: str,
    section: str,
    image: ImageSpec,
    image_path: str,
) -> str:
    if image_path in get_image_sources(markdown):
        raise ValueError(f"Image path already exists in Markdown: {image_path}")

    image_md = f"![{image.alt}]({image_path})\n*{image.caption}*"

    bounds = find_h2_section_bounds(
        markdown,
        section,
    )

    if image.placement == "start":
        insertion_line = bounds.heading_end_line

    elif image.placement == "middle":
        insertion_line = find_first_body_block_end(
            markdown,
            start_line=(bounds.heading_end_line),
            end_line=(bounds.section_end_line),
        )

    else:
        insertion_line = bounds.section_end_line

    result = _insert_at_line(
        markdown,
        line_index=insertion_line,
        image_md=image_md,
    )

    count = get_image_sources(result).count(image_path)

    if count != 1:
        raise ValueError(f"Image insertion failed for {image_path}.")

    return result
