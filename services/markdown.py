import re

from schemas.models import ImageSpec


def safe_filename(value: str) -> str:
    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        "_",
        value,
    )

    value = value.strip("_")

    return f"{value}.png"


def insert_image(
    markdown: str,
    section: str,
    image: ImageSpec,
    image_path: str,
) -> str:
    image_md = f"![{image.alt}]({image_path})\n*{image.caption}*"

    heading = f"## {section}"

    if heading not in markdown:
        return markdown

    section_start = markdown.index(heading)

    next_heading = markdown.find(
        "\n## ",
        section_start + len(heading),
    )

    if next_heading == -1:
        section_end = len(markdown)
    else:
        section_end = next_heading

    section_text = markdown[section_start:section_end]

    if image.placement == "start":
        replacement = f"{heading}\n\n{image_md}"

        section_text = section_text.replace(
            heading,
            replacement,
            1,
        )

    elif image.placement == "middle":
        paragraphs = section_text.split("\n\n")

        if len(paragraphs) >= 3:
            midpoint = max(
                2,
                len(paragraphs) // 2,
            )

            paragraphs.insert(
                midpoint,
                image_md,
            )

            section_text = "\n\n".join(paragraphs)

    else:
        section_text = section_text.rstrip() + "\n\n" + image_md + "\n"

    return markdown[:section_start] + section_text + markdown[section_end:]
