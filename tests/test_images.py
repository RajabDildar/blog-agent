from schemas.models import ImageSpec
from services.markdown import insert_image


def test_start_image_insertion():
    markdown = """# Blog

## Architecture

This explains the architecture.

## Security

Security details.
"""

    image = ImageSpec(
        id="img-1",
        section_id=1,
        image_type="technical_diagram",
        purpose="Explain the architecture.",
        visual_description=(
            "A system architecture showing the main components and their connections."
        ),
        key_elements=[
            "LLM",
            "tools",
            "memory",
        ],
        placement="start",
        alt="AI agent architecture",
        caption="A simplified agent architecture.",
    )

    result = insert_image(
        markdown=markdown,
        section="Architecture",
        image=image,
        image_path="../images/architecture.png",
    )

    assert "![AI agent architecture]" in result

    assert result.count("../images/architecture.png") == 1


def test_middle_image_falls_back_to_first_body_position():
    markdown = """# Blog

## Architecture

Only one paragraph.

## Security

Security details.
"""

    image = ImageSpec(
        id="img-2",
        section_id=1,
        image_type="technical_diagram",
        purpose="Explain the architecture.",
        visual_description=("A diagram showing the system components."),
        key_elements=[
            "LLM",
            "tools",
        ],
        placement="middle",
        alt="Architecture",
        caption="Architecture overview.",
    )

    result = insert_image(
        markdown=markdown,
        section="Architecture",
        image=image,
        image_path="../images/architecture.png",
    )

    assert result.count("../images/architecture.png") == 1
