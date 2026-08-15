import pytest

from schemas.models import ImageSpec
from services.markdown import insert_image
from services.markdown_parser import get_image_sources


def make_image(
    *,
    image_id: str = "img-1",
    placement: str = "middle",
    alt: str = "Architecture diagram",
) -> ImageSpec:
    return ImageSpec(
        id=image_id,
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
        placement=placement,
        alt=alt,
        caption="A simplified architecture overview.",
    )


def test_start_image_insertion():
    markdown = """# Blog

## Architecture

This explains the architecture.
## Security

Security details.
"""
    image = make_image(
        placement="start",
        alt="AI agent architecture",
    )

    result = insert_image(
        markdown=markdown,
        section="Architecture",
        image=image,
        image_path="../images/architecture.png",
    )

    assert "![AI agent architecture]" in result
    assert get_image_sources(result).count("../images/architecture.png") == 1

    heading_index = result.index("## Architecture")
    image_index = result.index("![AI agent architecture]")
    body_index = result.index("This explains the architecture.")

    assert heading_index < image_index < body_index


def test_middle_image_falls_back_to_first_body_position():
    markdown = """# Blog
## Architecture

Only one paragraph.
## Security

Security details.
"""
    image = make_image(placement="middle")

    result = insert_image(
        markdown=markdown,
        section="Architecture",
        image=image,
        image_path="../images/architecture.png",
    )

    image_index = result.index("![Architecture diagram]")
    paragraph_index = result.index("Only one paragraph.")
    security_index = result.index("## Security")

    assert paragraph_index < image_index < security_index
    assert get_image_sources(result).count("../images/architecture.png") == 1


def test_middle_insertion_does_not_split_fenced_code_block():
    markdown = """# Blog

## Architecture

```python
# comment
def build():
    return "agent"
```

Explanation after the code.

## Security

Security details.
"""
    image = make_image(placement="middle")

    result = insert_image(
        markdown=markdown,
        section="Architecture",
        image=image,
        image_path="../images/code-architecture.png",
    )

    closing_fence_index = result.index("```\n\n![Architecture diagram]")
    image_index = result.index("![Architecture diagram]")
    explanation_index = result.index("Explanation after the code.")

    assert closing_fence_index < image_index < explanation_index


def test_middle_insertion_does_not_split_gfm_table():
    markdown = """# Blog

## Architecture

| Component | Role |
| --- | --- |
| API | Entry point |
| Worker | Processing |

Explanation after the table.

## Security

Security details.
"""
    image = make_image(placement="middle")

    result = insert_image(
        markdown=markdown,
        section="Architecture",
        image=image,
        image_path="../images/table-architecture.png",
    )

    last_table_row_index = result.index("| Worker | Processing |")
    image_index = result.index("![Architecture diagram]")
    explanation_index = result.index("Explanation after the table.")

    assert last_table_row_index < image_index < explanation_index


def test_middle_insertion_does_not_split_blockquote():
    markdown = """# Blog

## Architecture

> First quoted line.
>
> Second quoted line.

Explanation after the quote.

## Security

Security details.
"""
    image = make_image(placement="middle")

    result = insert_image(
        markdown=markdown,
        section="Architecture",
        image=image,
        image_path="../images/quote-architecture.png",
    )

    second_quote_index = result.index("> Second quoted line.")
    image_index = result.index("![Architecture diagram]")
    explanation_index = result.index("Explanation after the quote.")

    assert second_quote_index < image_index < explanation_index


def test_middle_insertion_does_not_split_nested_list():
    markdown = """# Blog

## Architecture

- Runtime
  - router
  - workers
- Storage
  - artifacts

Explanation after the list.

## Security

Security details.
"""
    image = make_image(placement="middle")

    result = insert_image(
        markdown=markdown,
        section="Architecture",
        image=image,
        image_path="../images/list-architecture.png",
    )

    last_list_item_index = result.index("  - artifacts")
    image_index = result.index("![Architecture diagram]")
    explanation_index = result.index("Explanation after the list.")

    assert last_list_item_index < image_index < explanation_index


def test_end_insertion_ignores_fake_h2_inside_code():
    markdown = """# Blog

## Architecture

```markdown
## Security
This heading-looking text is code.
```

Architecture explanation.

## Security

Real security section.
"""
    image = make_image(
        placement="end",
        alt="Architecture end diagram",
    )

    result = insert_image(
        markdown=markdown,
        section="Architecture",
        image=image,
        image_path="../images/end-architecture.png",
    )

    code_close_index = result.index("```\n\nArchitecture explanation.")
    explanation_index = result.index("Architecture explanation.")
    image_index = result.index("![Architecture end diagram]")
    real_security_index = result.rindex("## Security")

    assert code_close_index < explanation_index < image_index < real_security_index


def test_existing_real_image_path_is_rejected():
    markdown = """# Blog

## Architecture

![Existing](../images/architecture.png)

Content.
"""
    image = make_image(placement="start")

    with pytest.raises(
        ValueError,
        match="Image path already exists in Markdown",
    ):
        insert_image(
            markdown=markdown,
            section="Architecture",
            image=image,
            image_path="../images/architecture.png",
        )


def test_image_like_syntax_inside_code_does_not_block_insertion():
    markdown = """# Blog

## Architecture

```markdown
![example](../images/architecture.png)
```

Content.
"""
    image = make_image(placement="end")

    result = insert_image(
        markdown=markdown,
        section="Architecture",
        image=image,
        image_path="../images/architecture.png",
    )

    assert get_image_sources(result) == [
        "../images/architecture.png",
    ]
