import re

from schemas.models import ImageSpec


def safe_stem(value: str) -> str:
    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        "_",
        value,
    )

    return value.strip("_")


def safe_image_filename(value: str) -> str:
    return f"{safe_stem(value)}.png"


def safe_blog_filename(value: str) -> str:
    return f"{safe_stem(value)}.md"


def _find_section_bounds(
    markdown: str,
    section: str,
) -> tuple[int, int, int]:
    pattern = re.compile(
        rf"^##\s+{re.escape(section)}\s*$",
        re.MULTILINE,
    )

    match = pattern.search(markdown)

    if match is None:
        raise ValueError(f"Section not found for image insertion: {section}")

    section_start = match.start()
    heading_end = match.end()

    next_heading = re.search(
        r"^##\s+.+$",
        markdown[heading_end:],
        re.MULTILINE,
    )

    if next_heading is None:
        section_end = len(markdown)
    else:
        section_end = heading_end + next_heading.start()

    return section_start, heading_end, section_end


def _insert_start(
    section_text: str,
    heading_end_offset: int,
    image_md: str,
) -> str:
    relative = heading_end_offset

    after_heading = section_text[:relative]

    remainder = section_text[relative:]

    return after_heading + "\n\n" + image_md + "\n" + remainder.lstrip("\n")


def _insert_middle(
    section_text: str,
    heading_end_offset: int,
    image_md: str,
) -> str:
    heading_part = section_text[:heading_end_offset]
    body = section_text[heading_end_offset:]

    body = body.lstrip("\n")

    paragraphs = [
        paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()
    ]

    if not paragraphs:
        return heading_part + "\n\n" + image_md + "\n"

    insert_at = 1

    paragraphs.insert(
        insert_at,
        image_md,
    )

    return heading_part.rstrip() + "\n\n" + "\n\n".join(paragraphs) + "\n"


def _insert_end(
    section_text: str,
    image_md: str,
) -> str:
    return section_text.rstrip() + "\n\n" + image_md + "\n"


def insert_image(
    *,
    markdown: str,
    section: str,
    image: ImageSpec,
    image_path: str,
) -> str:
    image_md = f"![{image.alt}]({image_path})\n*{image.caption}*"

    section_start, heading_end, section_end = _find_section_bounds(
        markdown,
        section,
    )

    section_text = markdown[section_start:section_end]

    relative_heading_end = heading_end - section_start

    if image.placement == "start":
        updated_section = _insert_start(
            section_text,
            relative_heading_end,
            image_md,
        )

    elif image.placement == "middle":
        updated_section = _insert_middle(
            section_text,
            relative_heading_end,
            image_md,
        )

    else:
        updated_section = _insert_end(
            section_text,
            image_md,
        )

    result = markdown[:section_start] + updated_section + markdown[section_end:]

    if result.count(image_path) != 1:
        raise ValueError(f"Image insertion failed for {image_path}.")

    return result
